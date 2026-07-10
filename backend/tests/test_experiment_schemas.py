import pytest
from pydantic import ValidationError

from backend.schemas.experiment_schema import ExperimentCreate, PromptFactors


def test_experiment_create_defaults_to_openai_and_all_factors_off():
    payload = ExperimentCreate(
        course="ENGR 101",
        topic="Statics",
        learning_objectives="Solve equilibrium problems.",
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=4,
    )

    assert payload.prompt_structure == "openai"
    assert payload.factors == PromptFactors()
    assert payload.estimated_time_minutes == 30
    assert payload.factors.concept_bridge is False
    assert payload.factors.few_shot is False
    assert payload.factors.reference_content is False
    assert payload.factors.reasoning_guidance is False


def test_experiment_create_accepts_anthropic_prompt_structure():
    payload = ExperimentCreate(
        course="ENGR 201",
        topic="Signals",
        learning_objectives="Analyze simple signals.",
        assessment_type="short_answer",
        difficulty="intermediate",
        number_of_questions=2,
        prompt_structure="anthropic",
        factors={"concept_bridge": True, "few_shot": True, "reference_content": False, "reasoning_guidance": False},
        factor_inputs={"concept_bridge": "Connect signals to vectors.", "few_shot": "Q: Example? A: Example."},
    )

    assert payload.prompt_structure == "anthropic"
    assert payload.factors.concept_bridge is True


def test_enabled_factor_requires_content():
    with pytest.raises(ValidationError):
        ExperimentCreate(course="ENGR", topic="Statics", learning_objectives="Resolve forces", difficulty="medium", factors={"reasoning_guidance": True})


def test_experiment_create_rejects_removed_frameworks():
    with pytest.raises(ValidationError):
        ExperimentCreate(
            course="ENGR 101",
            topic="Statics",
            learning_objectives="Solve equilibrium problems.",
            assessment_type="mixed",
            difficulty="introductory",
            number_of_questions=4,
            prompt_structure="forge",
        )
