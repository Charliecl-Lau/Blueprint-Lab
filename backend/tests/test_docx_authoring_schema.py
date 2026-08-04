import pytest
from pydantic import ValidationError

from backend.schemas.docx_authoring_schema import RewrittenAssessmentManifest


def manifest():
    options = [
        {"id": letter, "body": f"Option {letter}", "is_correct": letter == "A"}
        for letter in "ABCDE"
    ]
    return {
        "schema_version": "rewritten-assessment/1",
        "metadata": {"title": "Assessment", "course": "MSE", "topic": "Phases", "difficulty": "medium", "estimated_time_minutes": 20, "learning_objectives": ["Analyze phases"]},
        "questions": [{
            "id": "q1", "source_question_id": "11", "source_ordinal": 0,
            "title": "Phase rule", "body": "Choose the correct statement.",
            "options": options,
            "solution": {"kind": "conceptual", "governing_concept": "Phase rule", "application_steps": ["Identify variables"], "option_elimination": [{"option_id": letter, "explanation": f"Why {letter} is wrong"} for letter in "BCDE"], "conclusion": "Option A is correct"},
        }],
        "answer_key": [{"question_id": "q1", "correct_option_id": "A", "answer": "Option A"}],
        "overall_connection": "Connects thermodynamics to phase stability.",
        "quality_check": [{"question_id": "q1", "alignment": "yes", "correctness": "yes", "clarity": "yes", "accessibility": "yes"}],
        "revision_options": ["Increase difficulty", "Add a diagram", "Change context"],
    }


def test_rewritten_manifest_accepts_typed_complete_mcq():
    assert RewrittenAssessmentManifest.model_validate(manifest()).questions[0].source_ordinal == 0


@pytest.mark.parametrize("mutation", ["four_options", "two_correct", "missing_mapping", "untyped_solution", "duplicate_id"])
def test_rewritten_manifest_rejects_contract_violations(mutation):
    value = manifest()
    if mutation == "four_options": value["questions"][0]["options"].pop()
    elif mutation == "two_correct": value["questions"][0]["options"][1]["is_correct"] = True
    elif mutation == "missing_mapping": del value["questions"][0]["source_question_id"]
    elif mutation == "untyped_solution": del value["questions"][0]["solution"]["kind"]
    else: value["questions"].append(dict(value["questions"][0]))
    with pytest.raises(ValidationError):
        RewrittenAssessmentManifest.model_validate(value)
