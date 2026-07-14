from io import BytesIO
from zipfile import ZipFile

from docx import Document

from backend.services.docx_exporter import build_assessment_docx


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
