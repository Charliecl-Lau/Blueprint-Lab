from io import BytesIO
from zipfile import ZipFile

from docx import Document

from backend.services.docx_exporter import build_assessment_docx


def thermodynamic_equation_ast():
    return {
        "type": "equation",
        "left": {
            "type": "fraction",
            "numerator": {"type": "differential", "variable": "P"},
            "denominator": {"type": "differential", "variable": "T"},
        },
        "right": {
            "type": "fraction",
            "numerator": {"type": "symbol", "name": "DeltaH"},
            "denominator": {
                "type": "product",
                "terms": [
                    {"type": "symbol", "name": "T"},
                    {"type": "symbol", "name": "DeltaV"},
                ],
            },
        },
    }


def test_docx_contains_rich_research_content_and_native_word_equation():
    content = build_assessment_docx(
        run_id=12, prompt_id=34, condition_code="C101", run_number=2,
        course="MSE302", topic="Phase equilibrium",
        questions=[{
            "type": "mcq",
            "metadata": {
                "question_title": "Equilibrium condition",
                "concept_map_bridge": "Connects MSE202 free energy to MSE302 phase stability.",
                "materials_science_context": "Determines stable phases in an alloy.",
            },
            "body": "Which condition identifies phase equilibrium?",
            "options": [
                {"body": "Equal chemical potentials", "is_correct": True},
                {"body": "Unequal temperatures", "is_correct": False},
            ],
            "model_answer": "Chemical potentials are equal at equilibrium.",
            "equations": [{"label": "Equilibrium", "expression": "mu_alpha = mu_beta", "location": "solution"}],
            "quality_check": [{"criterion": "Correctness", "rating": 5, "comment": "Thermodynamically correct."}],
            "revision_options": ["Ask students to derive the equilibrium condition."],
        }],
    )

    document = Document(BytesIO(content))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Run ID: 12" in text
    assert "Prompt ID: 34" in text
    assert "Condition Code: C101" in text
    assert "Run Number: 2" in text
    assert "Connects MSE202 free energy to MSE302 phase stability." in text
    assert "Chemical potentials are equal at equilibrium." in text
    assert "Assessment Quality Check" not in text
    assert "Suggested Revision Options" in text
    assert "End-to-end token usage" not in text

    with ZipFile(BytesIO(content)) as archive:
        document_xml = archive.read("word/document.xml")
    assert b"<m:oMath" in document_xml
    assert document_xml.count(b"<m:sSub>") == 2
    assert "α".encode() in document_xml
    assert "β".encode() in document_xml


def test_docx_converts_flat_word_linear_equations_to_built_up_omml():
    content = build_assessment_docx(
        run_id=20, prompt_id=21, condition_code="C010", run_number=1,
        course="MSE202", topic="Thermodynamics",
        questions=[{
            "metadata": {},
            "body": "Evaluate the expressions.",
            "options": [],
            "model_answer": "Use the equations shown.",
            "equations": [
                {
                    "label": "Fraction",
                    "expression": "DeltaH/(T DeltaS)",
                    "location": "solution",
                },
                {
                    "label": "Scripts",
                    "expression": "x_a^2",
                    "location": "solution",
                },
                {
                    "label": "Radical",
                    "expression": "sqrt(x_a)",
                    "location": "solution",
                },
            ],
        }],
    )

    with ZipFile(BytesIO(content)) as archive:
        document_xml = archive.read("word/document.xml")

    assert b"<m:f>" in document_xml
    assert b"<m:num>" in document_xml
    assert b"<m:den>" in document_xml
    assert document_xml.count(b"<m:sSub>") >= 2
    assert b"<m:sSup>" in document_xml
    assert b"<m:rad>" in document_xml


def test_docx_replaces_equation_placeholders_inline_without_duplicate_blocks():
    content = build_assessment_docx(
        run_id=22, prompt_id=23, condition_code="C011", run_number=1,
        course="MSE202", topic="Thermodynamics",
        questions=[{
            "metadata": {},
            "body": "Use [[EQ:gibbs_formula]] to calculate the change.",
            "options": [{
                "body": "The value is [[EQ:option_value]].",
                "is_correct": True,
            }],
            "model_answer": (
                "Using [[EQ:option_value]], substitution gives [[EQ:final_result]]."
            ),
            "equations": [
                {
                    "label": "gibbs_formula",
                    "expression": "DeltaG=DeltaH-T DeltaS",
                    "location": "question",
                },
                {
                    "label": "option_value",
                    "expression": "x_a^2",
                    "location": "question",
                },
                {
                    "label": "final_result",
                    "expression": "DeltaG=-180 J/mol",
                    "location": "solution",
                },
            ],
        }],
    )

    with ZipFile(BytesIO(content)) as archive:
        document_xml = archive.read("word/document.xml")

    assert b"[[EQ:" not in document_xml
    assert document_xml.count(b"<m:oMath>") == 4
    assert b"gibbs_formula:" not in document_xml
    assert b"option_value:" not in document_xml
    assert b"final_result:" not in document_xml
    assert b"<m:sSup>" in document_xml


def test_docx_omits_end_to_end_token_usage():
    content = build_assessment_docx(
        run_id=1,
        prompt_id=2,
        condition_code="C100",
        run_number=1,
        course="ENGR 101",
        topic="Statics",
        questions=[],
    )

    document = Document(BytesIO(content))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "End-to-end token usage" not in text
    assert "Input:" not in text
    assert "Model calls:" not in text


def test_docx_builds_embedded_structured_math_as_semantic_omml():
    equation = thermodynamic_equation_ast()
    content = build_assessment_docx(
        run_id=7,
        prompt_id=8,
        condition_code="C111",
        run_number=1,
        course="MSE302",
        topic="Phase transformations",
        questions=[{
            "metadata": {"question_title": "Clapeyron relation"},
            "body": "Use dP/dT = Delta H / (T * Delta V) to calculate the slope.",
            "body_segments": [
                {"type": "text", "text": "Use "},
                {"type": "math", "math": equation},
                {"type": "text", "text": " to calculate the slope."},
            ],
            "options": [{
                "body": "dP/dT = Delta H / (T * Delta V)",
                "is_correct": True,
                "segments": [{"type": "math", "math": equation}],
            }],
            "model_answer": "Apply dP/dT = Delta H / (T * Delta V).",
            "model_answer_segments": [
                {"type": "text", "text": "Apply "},
                {"type": "math", "math": equation},
                {"type": "text", "text": "."},
            ],
        }],
    )

    with ZipFile(BytesIO(content)) as archive:
        document_xml = archive.read("word/document.xml")

    assert document_xml.count(b"<m:oMath>") == 3
    assert document_xml.count(b"<m:f>") == 6
    assert b"<m:num>" in document_xml
    assert b"<m:den>" in document_xml
    assert "ΔH".encode() in document_xml
    assert "ΔV".encode() in document_xml
    assert b"dP/dT" not in document_xml


def test_docx_serializes_scripts_radicals_and_matrices_to_omml():
    content = build_assessment_docx(
        run_id=9,
        prompt_id=10,
        condition_code="C010",
        run_number=1,
        course="MATH",
        topic="Structured math",
        questions=[{
            "metadata": {},
            "body": "Inspect the expressions.",
            "options": [],
            "model_answer": "See the native equations.",
            "equations": [
                {
                    "label": "Subscript",
                    "math": {
                        "type": "subscript",
                        "base": {"type": "symbol", "name": "x"},
                        "subscript": {"type": "number", "value": "1"},
                    },
                    "location": "solution",
                },
                {
                    "label": "Power",
                    "math": {
                        "type": "superscript",
                        "base": {"type": "symbol", "name": "x"},
                        "superscript": {"type": "number", "value": "2"},
                    },
                    "location": "solution",
                },
                {
                    "label": "Root",
                    "math": {
                        "type": "radical",
                        "radicand": {"type": "symbol", "name": "x"},
                    },
                    "location": "solution",
                },
                {
                    "label": "Matrix",
                    "math": {
                        "type": "matrix",
                        "rows": [
                            [
                                {"type": "number", "value": "1"},
                                {"type": "number", "value": "0"},
                            ],
                            [
                                {"type": "number", "value": "0"},
                                {"type": "number", "value": "1"},
                            ],
                        ],
                    },
                    "location": "solution",
                },
            ],
        }],
    )

    with ZipFile(BytesIO(content)) as archive:
        document_xml = archive.read("word/document.xml")

    for tag in (b"<m:sSub>", b"<m:sSup>", b"<m:rad>", b"<m:m>", b"<m:mr>"):
        assert tag in document_xml
