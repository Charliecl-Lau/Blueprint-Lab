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
    assert "Assessment Quality Check" in text
    assert "Suggested Revision Options" in text
    assert "End-to-end token usage" in text
    assert "Not recorded." in text

    with ZipFile(BytesIO(content)) as archive:
        document_xml = archive.read("word/document.xml")
    assert b"<m:oMath" in document_xml
    assert b"mu_alpha = mu_beta" in document_xml


def test_docx_contains_recorded_end_to_end_token_usage():
    content = build_assessment_docx(
        run_id=1,
        prompt_id=2,
        condition_code="C100",
        run_number=1,
        course="ENGR 101",
        topic="Statics",
        questions=[],
        token_usage={
            "input_tokens": 30,
            "output_tokens": 12,
            "total_tokens": 42,
            "model_calls": 2,
            "recording_state": "recorded",
            "stages": [],
        },
    )

    document = Document(BytesIO(content))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "End-to-end token usage" in text
    assert "Input: 30" in text
    assert "Output: 12" in text
    assert "Total: 42" in text
    assert "Model calls: 2" in text


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
