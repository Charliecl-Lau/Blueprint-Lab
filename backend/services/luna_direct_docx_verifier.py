"""Structural and canonical-content verification for Luna-authored DOCX files."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections import Counter

from lxml import etree

from backend.services.docx_package_verifier import DocxPackageVerifier
from backend.services.docx_verification import VerificationIssue, VerificationReport
from backend.services.reproducibility import canonical_json, sha256_text


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_EQ_REFERENCE = re.compile(r"\[\[EQ:[A-Za-z0-9_-]+\]\]")
_EQ_LABEL_REFERENCE = re.compile(r"\[\[EQ:([A-Za-z0-9_-]+)\]\]")
_RAW_LINEAR_MATH = re.compile(r"[_^]|\\(?:alpha|beta|gamma|delta|frac|sqrt)\b")
_FUNCTION_SOURCE = re.compile(r"\b(?:ln|exp|sin|cos|tan)\s*\(", re.IGNORECASE)
_GREEK_SOURCE = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "mu": "μ",
    "Delta": "Δ",
    "Phi": "Φ",
    "kappa": "κ",
}
_STRUCTURED_GREEK = {
    "Alpha": "Α", "Beta": "Β", "Gamma": "Γ", "Delta": "Δ",
    "Theta": "Θ", "Lambda": "Λ", "Mu": "Μ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "epsilon": "ε", "theta": "θ", "lambda": "λ", "mu": "μ",
    "nu": "ν", "pi": "π", "rho": "ρ", "sigma": "σ",
    "tau": "τ", "phi": "φ", "chi": "χ", "psi": "ψ",
    "omega": "ω",
}
_METADATA_LABELS = {
    "prompt_template_id": "Prompt Template ID",
    "actual_prompt_id": "Actual Prompt ID",
    "output_id": "Output ID",
    "final_question_id": "Final Question ID",
    "question_title": "Question Title",
    "course": "Course",
    "topic": "Topic",
    "question_type": "Question Type",
    "number_of_questions": "Number of Questions",
    "difficulty_level": "Difficulty Level",
    "cognitive_demand": "Cognitive Demand",
    "intended_assessment_setting": "Intended Assessment Setting",
    "mse202_concepts": "MSE202 Concept(s)",
    "mse302_concepts": "MSE302 Concept(s)",
    "concept_map_bridge": "Concept-Map Bridge",
    "materials_science_context": "Materials Science Context",
    "numerical_computation": "Numerical Computation",
    "estimated_time": "Estimated Time",
    "estimated_time_minutes": "Estimated Time",
    "learning_objectives": "Learning Objective(s)",
    "prompt_design_factors": "Prompt Design Factors",
    "additional_instructions": "Additional Instructions",
}


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _canonical_fragments(value: str | None) -> list[str]:
    return [
        normalized
        for part in _EQ_REFERENCE.split(value or "")
        if (normalized := _normalize(part))
    ]


def _content_text(value, fallback: str | None) -> str | None:
    if not isinstance(value, list):
        return fallback
    parts = [
        item.get("text", "")
        for item in value
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    return "".join(parts) or fallback


def _paragraph_texts(root) -> list[str]:
    namespaces = {"w": _W_NS, "m": _M_NS}
    return [
        _normalize(
            "".join(
                paragraph.xpath(
                    ".//w:t/text() | .//m:t/text()", namespaces=namespaces
                )
            )
        )
        for paragraph in root.xpath("//w:body/w:p", namespaces=namespaces)
    ]


def _heading_index(paragraphs: list[str], pattern: str) -> int | None:
    matcher = re.compile(pattern, re.IGNORECASE)
    return next(
        (index for index, text in enumerate(paragraphs) if matcher.fullmatch(text)),
        None,
    )


def _metadata_value(value) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _on_off_enabled(element, *, default: bool = True) -> bool:
    """Interpret the OOXML on/off values used by table properties."""
    if element is None:
        return False
    value = element.get(f"{{{_W_NS}}}val")
    if value is None:
        return default
    return value.casefold() not in {"0", "false", "off", "no"}


def _metadata_values_match(rendered: str | None, canonical) -> bool:
    if rendered is None:
        return False
    expected = _normalize(_metadata_value(canonical))
    actual = _normalize(rendered)
    if actual == expected:
        return True
    if not isinstance(canonical, list):
        return False
    # A comma-separated list is a normal Word-table presentation. The prompt
    # prefers semicolons, but the delimiter is formatting rather than canonical
    # assessment content.
    comma_separated = ", ".join(str(item) for item in canonical)
    return actual == _normalize(comma_separated)


def _metadata_table(root) -> tuple[list[tuple[str, str]], bool]:
    namespaces = {"w": _W_NS}
    for table in root.xpath("//w:tbl", namespaces=namespaces):
        rows = []
        for row in table.xpath("./w:tr", namespaces=namespaces):
            cells = [
                _normalize("".join(cell.xpath(".//w:t/text()", namespaces=namespaces)))
                for cell in row.xpath("./w:tc", namespaces=namespaces)
            ]
            if len(cells) >= 2:
                rows.append((cells[0], cells[1]))
        if rows and tuple(value.casefold() for value in rows[0]) == ("field", "entry"):
            first_row = table.xpath("./w:tr[1]", namespaces=namespaces)[0]
            repeated_header = next(
                iter(first_row.xpath("./w:trPr/w:tblHeader", namespaces=namespaces)),
                None,
            )
            table_look = next(
                iter(table.xpath("./w:tblPr/w:tblLook", namespaces=namespaces)),
                None,
            )
            first_row_styled = bool(
                table_look is not None
                and table_look.get(f"{{{_W_NS}}}firstRow", "").casefold()
                in {"1", "true", "on", "yes"}
            )
            accessible_header = _on_off_enabled(repeated_header) or first_row_styled
            return rows[1:], accessible_header
    return [], False


def _placeholder_placement(value: str, start: int, end: int) -> str:
    line_start = value.rfind("\n", 0, start) + 1
    line_end = value.find("\n", end)
    if line_end < 0:
        line_end = len(value)
    before = value[line_start:start].strip()
    after = value[end:line_end].strip()
    after_without_punctuation = re.sub(r"[.,;:!?]+", "", after).strip()
    return "display" if not before and not after_without_punctuation else "inline"


def _referenced_equation_placements(
    questions: list[dict],
) -> list[tuple[dict, str]]:
    ordered: list[tuple[dict, str]] = []
    included: set[int] = set()
    for location in ("question", "solution"):
        for question in questions:
            equations = {
                item.get("label"): item for item in question.get("equations") or []
            }
            texts = (
                [question.get("body")]
                + [option.get("body") for option in question.get("options") or []]
                if location == "question"
                else [question.get("model_answer")]
            )
            found = False
            for value in texts:
                text = value or ""
                for match in _EQ_LABEL_REFERENCE.finditer(text):
                    label = match.group(1)
                    equation = equations.get(label)
                    if equation is not None:
                        ordered.append(
                            (
                                equation,
                                _placeholder_placement(
                                    text, match.start(), match.end()
                                ),
                            )
                        )
                        included.add(id(equation))
                        found = True
            if not found:
                for item in question.get("equations") or []:
                    if item.get("location") == location and id(item) not in included:
                        ordered.append((item, "display"))
                        included.add(id(item))
    return ordered


def _referenced_equations(questions: list[dict]) -> list[dict]:
    return [equation for equation, _ in _referenced_equation_placements(questions)]


def _structured_math_requirements(node) -> tuple[Counter, set[str]]:
    required: Counter = Counter()
    glyphs: set[str] = set()

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        kind = value.get("type")
        structure = {
            "delimiter": "delimiter",
            "function": "function",
            "fraction": "fraction",
            "subscript": "subscript",
            "superscript": "superscript",
            "radical": "radical",
            "matrix": "matrix",
        }.get(kind)
        if structure:
            required[structure] += 1
        if kind == "symbol":
            glyph = _STRUCTURED_GREEK.get(value.get("name"))
            if glyph:
                glyphs.add(glyph)
        for child in value.values():
            if isinstance(child, (dict, list)):
                visit(child)

    visit(node)
    return required, glyphs


def _equation_structure_errors(equation, equation_entry: dict) -> list[str]:
    namespaces = {"m": _M_NS}
    errors = []
    structured_math = equation_entry.get("math")
    if isinstance(structured_math, dict):
        required, required_glyphs = _structured_math_requirements(structured_math)
        actual = {
            "delimiter": len(equation.xpath(".//m:d", namespaces=namespaces)),
            "function": len(equation.xpath(".//m:func", namespaces=namespaces)),
            "fraction": len(equation.xpath(".//m:f", namespaces=namespaces)),
            "subscript": len(
                equation.xpath(".//m:sSub | .//m:sSubSup", namespaces=namespaces)
            ),
            "superscript": len(
                equation.xpath(".//m:sSup | .//m:sSubSup", namespaces=namespaces)
            ),
            "radical": len(equation.xpath(".//m:rad", namespaces=namespaces)),
            "matrix": len(equation.xpath(".//m:m", namespaces=namespaces)),
        }
        for structure, expected_count in required.items():
            found_count = actual[structure]
            if found_count < expected_count:
                errors.append(
                    f"{structure} expected {expected_count}, found {found_count}"
                )
        math_text = "".join(
            equation.xpath(".//m:t/text()", namespaces=namespaces)
        )
        for glyph in sorted(required_glyphs):
            if glyph not in math_text:
                errors.append(f"greek glyph {glyph}")
        return errors

    expression = equation_entry.get("expression") or ""
    if "_" in expression and not equation.xpath(
        ".//m:sSub | .//m:sSubSup", namespaces=namespaces
    ):
        errors.append("subscript")
    if "^" in expression and not equation.xpath(
        ".//m:sSup | .//m:sSubSup", namespaces=namespaces
    ):
        errors.append("superscript")
    if "/" in expression and not equation.xpath(".//m:f", namespaces=namespaces):
        errors.append("fraction")
    if _FUNCTION_SOURCE.search(expression) and not equation.xpath(
        ".//m:func", namespaces=namespaces
    ):
        errors.append("function")
    math_text = "".join(equation.xpath(".//m:t/text()", namespaces=namespaces))
    for source, glyph in _GREEK_SOURCE.items():
        if re.search(
            rf"(?<![A-Za-z]){re.escape(source)}(?![a-z])", expression
        ) and glyph not in math_text:
            errors.append(f"greek:{source}")
    return errors


class LunaDirectDocxVerifier:
    def __init__(self, package_verifier: DocxPackageVerifier | None = None):
        self.package_verifier = package_verifier or DocxPackageVerifier()

    def verify(self, content: bytes, assessment_json: dict) -> VerificationReport:
        package_hash = hashlib.sha256(content).hexdigest()
        manifest_hash = sha256_text(canonical_json(assessment_json))
        package_report = self.package_verifier.verify(content)
        if not package_report.valid:
            evidence = ",".join(issue.code for issue in package_report.issues)
            return VerificationReport(
                valid=False,
                issues=(VerificationIssue(
                    "docx_package_invalid",
                    repairable=all(issue.repairable for issue in package_report.issues),
                    evidence=evidence,
                ),),
                package_sha256=package_hash,
                manifest_sha256=manifest_hash,
                tool_versions={"luna_direct_verifier": "4", "package_verifier": "1"},
            )

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                xml = archive.read("word/document.xml")
                names = archive.namelist()
                header_xml = [
                    archive.read(name)
                    for name in names
                    if re.fullmatch(r"word/header\d*\.xml", name)
                ]
                footer_xml = [
                    archive.read(name)
                    for name in names
                    if re.fullmatch(r"word/footer\d*\.xml", name)
                ]
                relationships = archive.read("word/_rels/document.xml.rels")
            parser = etree.XMLParser(
                resolve_entities=False,
                no_network=True,
                recover=False,
                huge_tree=False,
            )
            root = etree.fromstring(xml, parser=parser)
        except (KeyError, OSError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
            return VerificationReport(
                valid=False,
                issues=(
                    VerificationIssue(
                        "docx_package_invalid",
                        evidence=f"main document XML unavailable: {type(exc).__name__}",
                    ),
                ),
                package_sha256=package_hash,
                manifest_sha256=manifest_hash,
                tool_versions={"luna_direct_verifier": "4", "package_verifier": "1"},
            )

        visible = _normalize(" ".join(root.xpath("//w:t/text()", namespaces={"w": _W_NS})))
        issues: list[VerificationIssue] = []
        if _EQ_REFERENCE.search(visible):
            issues.append(VerificationIssue("equation_placeholder_unresolved"))

        questions = assessment_json.get("questions", [])
        metadata = assessment_json.get("assessment_metadata") or {}
        metadata_rows, accessible_metadata_header = _metadata_table(root)
        if metadata and not metadata_rows:
            issues.append(VerificationIssue("assessment_metadata_table_missing"))
        elif metadata:
            rendered_metadata = dict(metadata_rows)
            for key, value in metadata.items():
                label = _METADATA_LABELS.get(key)
                actual = rendered_metadata.get(label) if label is not None else None
                if label is None or not _metadata_values_match(actual, value):
                    expected = _metadata_value(value)
                    issues.append(
                        VerificationIssue(
                            "assessment_metadata_invalid",
                            evidence=(
                                f"field {key}: expected label {label or '<unsupported>'!r} "
                                f"with value {expected!r}; found {actual!r}"
                            ),
                        )
                    )
            if any(re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", label) for label in rendered_metadata):
                issues.append(VerificationIssue("assessment_metadata_raw_key"))
            if not accessible_metadata_header:
                issues.append(
                    VerificationIssue(
                        "assessment_metadata_header_invalid",
                        evidence=(
                            "mark the Field/Entry row with w:tblHeader or set "
                            "w:tblLook w:firstRow to an enabled value"
                        ),
                    )
                )
        for index, question in enumerate(questions):
            body = _content_text(question.get("body_segments"), question.get("body"))
            if any(fragment not in visible for fragment in _canonical_fragments(body)):
                issues.append(
                    VerificationIssue(
                        "canonical_question_missing", evidence=f"question index {index}"
                    )
                )
            answer = _content_text(
                question.get("model_answer_segments"), question.get("model_answer")
            )
            if any(fragment not in visible for fragment in _canonical_fragments(answer)):
                issues.append(
                    VerificationIssue(
                        "canonical_solution_missing", evidence=f"question index {index}"
                    )
                )

        paragraphs = _paragraph_texts(root)
        questions_heading = _heading_index(
            paragraphs, r"(?:\d+\.\s*)?Student-Facing Questions"
        )
        solutions_heading = _heading_index(
            paragraphs, r"(?:\d+\.\s*)?Fully Worked Solutions"
        )
        question_headings = [
            _heading_index(
                paragraphs,
                rf"Question {index + 1}(?:\s*[-\u2013\u2014].*)?",
            )
            for index in range(len(questions))
        ]
        solution_headings = [
            _heading_index(
                paragraphs,
                rf"Solution {index + 1}(?:\s*[-\u2013\u2014].*)?",
            )
            for index in range(len(questions))
        ]
        ordered_headings = [
            questions_heading,
            *question_headings,
            solutions_heading,
            *solution_headings,
        ]
        if (
            any(index is None for index in ordered_headings)
            or ordered_headings != sorted(ordered_headings)
        ):
            issues.append(VerificationIssue("assessment_section_order_invalid"))

        expected_equation_placements = _referenced_equation_placements(questions)
        expected_equations = len(expected_equation_placements)
        native_equations = root.xpath("//m:oMath", namespaces={"m": _M_NS})
        if expected_equations and not native_equations:
            issues.append(VerificationIssue("native_equation_missing"))
        elif len(native_equations) != expected_equations:
                issues.append(
                    VerificationIssue(
                        "native_equation_count_mismatch",
                        evidence=f"expected {expected_equations}, found {len(native_equations)} native equations",
                        expected={"count": expected_equations},
                        actual={"count": len(native_equations)},
                    )
                )
        for index, equation in enumerate(native_equations):
            container = equation.getparent()
            actual_placement = (
                "display"
                if container.tag == f"{{{_M_NS}}}oMathPara"
                else "inline"
            )
            if index < len(expected_equation_placements):
                equation_entry, expected_placement = expected_equation_placements[index]
            else:
                equation_entry, expected_placement = None, None
            if expected_placement != actual_placement or (
                actual_placement == "inline"
                and container.tag != f"{{{_W_NS}}}p"
            ):
                issues.append(
                    VerificationIssue(
                        "native_equation_placement_invalid",
                        evidence=(
                            f"equation index {index}: expected {expected_placement}, "
                            f"found {actual_placement}"
                        ),
                        target={
                            "equation_label": (equation_entry or {}).get("label"),
                            "equation_index": index,
                        },
                        expected={"placement": expected_placement},
                        actual={"placement": actual_placement},
                    )
                )
            if actual_placement == "display":
                justification = container.xpath(
                    "./m:oMathParaPr/m:jc",
                    namespaces={"m": _M_NS},
                )
                # ISO/IEC 29500 defines an omitted m:jc (and one without m:val)
                # as centerGroup. Only an explicit non-centred value violates
                # the display-equation contract.
                justification_value = (
                    justification[0].get(f"{{{_M_NS}}}val")
                    if justification
                    else None
                )
                if justification_value not in {None, "center", "centerGroup"}:
                    issues.append(
                        VerificationIssue(
                            "native_equation_display_invalid",
                            evidence=(
                                f"equation index {index}: explicit justification "
                                f"{justification_value!r} is not centered"
                            ),
                        )
                    )
            if equation_entry is not None:
                missing = _equation_structure_errors(
                    equation, equation_entry
                )
                if missing:
                    issues.append(
                        VerificationIssue(
                            "native_equation_structure_invalid",
                            evidence=(
                                f"equation label {(equation_entry or {}).get('label') or '<unknown>'} "
                                f"at index {index}: {','.join(missing)}"
                            ),
                            target={
                                "equation_label": (equation_entry or {}).get("label"),
                                "equation_index": index,
                            },
                            expected={"required_constructs": missing},
                            actual={"missing_constructs": missing},
                        )
                    )
        raw_math_text = " ".join(
            root.xpath("//m:oMath//m:t/text()", namespaces={"m": _M_NS})
        )
        if _RAW_LINEAR_MATH.search(raw_math_text):
            issues.append(VerificationIssue("native_equation_structure_invalid"))

        for index, drawing in enumerate(
            root.xpath("//w:drawing", namespaces={"w": _W_NS})
        ):
            properties = drawing.xpath(
                ".//wp:docPr", namespaces={"wp": _WP_NS}
            )
            alternative_text = "" if not properties else (
                properties[0].get("descr") or properties[0].get("title") or ""
            )
            if not alternative_text.strip():
                issues.append(
                    VerificationIssue(
                        "image_alt_text_missing",
                        evidence=f"drawing index {index}",
                    )
                )

        relationship_text = relationships.decode("utf-8", errors="ignore")
        if not header_xml or "/header" not in relationship_text:
            issues.append(VerificationIssue("header_missing"))
        if not footer_xml or "/footer" not in relationship_text:
            issues.append(VerificationIssue("footer_missing"))
        else:
            footer_text = " ".join(
                data.decode("utf-8", errors="ignore") for data in footer_xml
            )
            if "PAGE" not in footer_text or "NUMPAGES" not in footer_text:
                issues.append(VerificationIssue("page_fields_missing"))

        return VerificationReport(
            valid=not issues,
            issues=tuple(issues),
            package_sha256=package_hash,
            manifest_sha256=manifest_hash,
            tool_versions={"luna_direct_verifier": "6", "package_verifier": "1"},
        )
