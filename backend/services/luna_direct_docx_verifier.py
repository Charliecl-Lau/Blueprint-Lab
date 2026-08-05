"""Structural and canonical-content verification for Luna-authored DOCX files."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile

from lxml import etree

from backend.services.docx_package_verifier import DocxPackageVerifier
from backend.services.docx_verification import VerificationIssue, VerificationReport
from backend.services.reproducibility import canonical_json, sha256_text


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_EQ_REFERENCE = re.compile(r"\[\[EQ:[A-Za-z0-9_-]+\]\]")


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
                issues=(VerificationIssue("docx_package_invalid", evidence=evidence),),
                package_sha256=package_hash,
                manifest_sha256=manifest_hash,
                tool_versions={"luna_direct_verifier": "1", "package_verifier": "1"},
            )

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                xml = archive.read("word/document.xml")
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
                tool_versions={"luna_direct_verifier": "1", "package_verifier": "1"},
            )

        visible = _normalize(" ".join(root.xpath("//w:t/text()", namespaces={"w": _W_NS})))
        issues: list[VerificationIssue] = []
        if _EQ_REFERENCE.search(visible):
            issues.append(VerificationIssue("equation_placeholder_unresolved"))

        questions = assessment_json.get("questions", [])
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

        requires_native_math = any(question.get("equations") for question in questions)
        has_native_math = bool(
            root.xpath("//m:oMath | //m:oMathPara", namespaces={"m": _M_NS})
        )
        if requires_native_math and not has_native_math:
            issues.append(VerificationIssue("native_equation_missing"))

        return VerificationReport(
            valid=not issues,
            issues=tuple(issues),
            package_sha256=package_hash,
            manifest_sha256=manifest_hash,
            tool_versions={"luna_direct_verifier": "1", "package_verifier": "1"},
        )
