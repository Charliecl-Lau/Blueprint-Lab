import copy

import pytest

from backend.schemas.assessment_schema import (
    ProviderAssessmentGenerationResponse,
    ProviderSegmentReplacement,
)
from backend.services.assessment_local_repair import (
    LocalizedRepairRejected,
    apply_segment_replacement,
    segment_target,
)


def _metadata(question_count=1):
    return {
        "question_title": "Localized repair fixture",
        "course": "MSE302",
        "topic": "Thermodynamics",
        "question_type": "long_answer",
        "number_of_questions": question_count,
        "difficulty_level": "advanced",
        "cognitive_demand": "Analyze",
        "intended_assessment_setting": "Exam",
        "mse202_concepts": ["Energy"],
        "mse302_concepts": ["Chemical potential"],
        "concept_map_bridge": None,
        "materials_science_context": "Solutions",
        "numerical_computation": "None",
        "estimated_time": "10 minutes",
        "learning_objectives": ["Analyze activity"],
        "prompt_design_factors": [],
    }


def _question(title, body_segments, answer_segments):
    return {
        "type": "long_answer",
        "metadata": {
            "question_title": title,
            "question_type": "long_answer",
            "difficulty_level": "advanced",
            "mse202_concepts": ["Energy"],
            "mse302_concepts": ["Chemical potential"],
            "concept_map_bridge": None,
            "materials_science_context": "Solutions",
            "estimated_time_minutes": 10,
            "learning_objectives": ["Analyze activity"],
        },
        "body_segments": body_segments,
        "options": [],
        "model_answer_segments": answer_segments,
        "quality_checks": [{"criterion": "Correct", "rating": 5, "comment": "Yes"}],
        "revision_options": ["Variant A", "Variant B"],
    }


def _provider():
    questions = [
        _question(
            "Q1",
            [{"type": "text", "text": "Unaffected question."}],
            [{"type": "text", "text": "Unaffected answer."}],
        ),
        _question(
            "Q2",
            [{"type": "text", "text": "Also unaffected."}],
            [{"type": "text", "text": "Also unaffected answer."}],
        ),
        _question(
            "Q3",
            [{"type": "text", "text": "Explain chemical potential."}],
            [
                {"type": "text", "text": "Step 1. "},
                {"type": "text", "text": "Step 2. "},
                {"type": "text", "text": "Step 3. "},
                {"type": "text", "text": "mu_A = mu_A^0 + RT ln(a_A)"},
                {"type": "text", "text": ". Step 5."},
            ],
        ),
    ]
    return ProviderAssessmentGenerationResponse.model_validate(
        {"assessment_metadata": _metadata(len(questions)), "questions": questions}
    )


def test_solution_segment_patch_preserves_every_non_target_node():
    provider = _provider()
    before = provider.model_dump(mode="json")
    target = segment_target(
        provider, "questions.2.model_answer_segments.3.text"
    )
    replacement = ProviderSegmentReplacement.model_validate(
        {
            "segments": [
                {"type": "math", "expression": "mu_A = mu_A^0 + RT ln(a_A)", "display": True}
            ]
        }
    )

    patched = apply_segment_replacement(provider, target, replacement)
    after = patched.model_dump(mode="json")

    assert after["questions"][:2] == before["questions"][:2]
    assert after["questions"][2]["body_segments"] == before["questions"][2]["body_segments"]
    assert after["questions"][2]["model_answer_segments"][:3] == before["questions"][2]["model_answer_segments"][:3]
    assert after["questions"][2]["model_answer_segments"][4:] == before["questions"][2]["model_answer_segments"][4:]
    assert after["questions"][2]["model_answer_segments"][3]["type"] == "math"


def test_repair_rejects_numerical_or_wording_mutation():
    provider = _provider()
    original = copy.deepcopy(provider.model_dump(mode="json"))
    target = segment_target(provider, "questions.2.model_answer_segments.3.text")
    replacement = ProviderSegmentReplacement.model_validate(
        {
            "segments": [
                {"type": "math", "expression": "mu_A = mu_A^0 + 2RT ln(a_A)", "display": True}
            ]
        }
    )

    with pytest.raises(LocalizedRepairRejected, match="wording, notation, or numerical"):
        apply_segment_replacement(provider, target, replacement)

    assert provider.model_dump(mode="json") == original
