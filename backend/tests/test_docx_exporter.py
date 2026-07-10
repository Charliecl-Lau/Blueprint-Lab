from io import BytesIO
from zipfile import ZipFile

from docx import Document

from backend.services.docx_exporter import build_assessment_docx


def test_docx_contains_rich_research_content_and_native_word_equation():
    content = build_assessment_docx(
        assessment_id=12, prompt_id=34,
        condition_label="CourseBridge=ON; FewShot=OFF; Documents=ON",
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
    assert "Assessment ID: 12" in text
    assert "Prompt ID: 34" in text
    assert "CourseBridge=ON; FewShot=OFF; Documents=ON" in text
    assert "Connects MSE202 free energy to MSE302 phase stability." in text
    assert "Chemical potentials are equal at equilibrium." in text
    assert "Assessment Quality Check" in text
    assert "Suggested Revision Options" in text

    with ZipFile(BytesIO(content)) as archive:
        document_xml = archive.read("word/document.xml")
    assert b"<m:oMath" in document_xml
    assert b"mu_alpha = mu_beta" in document_xml
