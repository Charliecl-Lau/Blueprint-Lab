from copy import deepcopy

import pytest

from backend.schemas.assessment_schema import ProviderAssessmentGenerationResponse
from backend.services.assessment_segment_compiler import (
    AssessmentCompilationError,
    compile_provider_assessment,
)
from backend.tests.test_worker import (
    complete_assessment_metadata,
    complete_question,
)


def segmented_question():
    metadata = complete_question(
        question_type="short_answer",
        body="unused",
        model_answer="unused",
    )["metadata"]
    return {
        "type": "short_answer",
        "metadata": metadata,
        "body_segments": [
            {"type": "text", "text": "For "},
            {"type": "math", "expression": "x_a = 0.4", "display": False},
            {"type": "text", "text": ", determine the result."},
        ],
        "options": [],
        "model_answer_segments": [
            {"type": "text", "text": "Apply "},
            {
                "type": "math",
                "expression": "G_mix = H_mix - T S_mix",
                "display": True,
            },
            {"type": "text", "text": " and interpret the sign."},
        ],
        "quality_checks": [{
            "criterion": "Technical correctness",
            "rating": 5,
            "comment": "The relation is applied correctly.",
        }],
        "revision_options": [
            "Add numerical values.",
            "Ask for a physical interpretation.",
        ],
    }


def provider(question=None):
    return ProviderAssessmentGenerationResponse.model_validate({
        "assessment_metadata": complete_assessment_metadata(),
        "questions": [question or segmented_question()],
    })


def test_compiler_assigns_deterministic_labels_and_locations():
    first = compile_provider_assessment(provider())
    second = compile_provider_assessment(provider())

    assert first.model_dump() == second.model_dump()
    question = first.questions[0]
    assert question.body == (
        "For [[EQ:q1_question_body_m1]], determine the result."
    )
    assert question.model_answer == (
        "Apply [[EQ:q1_solution_model_answer_m1]] and interpret the sign."
    )
    assert [item.location for item in question.equations] == [
        "question",
        "solution",
    ]
    assert len({item.label for item in question.equations}) == 2


def test_compiler_reports_all_raw_math_text_segments_together():
    question = deepcopy(segmented_question())
    question["body_segments"] = [{
        "type": "text",
        "text": "Use x_a = 0.4.",
    }]
    question["model_answer_segments"] = [{
        "type": "text",
        "text": "Then C_p = 25 J/(mol K).",
    }]

    with pytest.raises(AssessmentCompilationError) as caught:
        compile_provider_assessment(provider(question))

    issues = caught.value.issues
    assert [item.code for item in issues] == [
        "raw_math_in_text_segment",
        "raw_math_in_text_segment",
    ]
    assert [item.field_path for item in issues] == [
        "questions.0.body_segments.0.text",
        "questions.0.model_answer_segments.0.text",
    ]
    assert all(item.question_ordinal == 0 for item in issues)
