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
    assert payload.factors.course_bridge is False
    assert payload.factors.few_shot is False
    assert payload.factors.documents is False


def test_experiment_create_accepts_anthropic_prompt_structure():
    payload = ExperimentCreate(
        course="ENGR 201",
        topic="Signals",
        learning_objectives="Analyze simple signals.",
        assessment_type="short_answer",
        difficulty="intermediate",
        number_of_questions=2,
        prompt_structure="anthropic",
        factors={"course_bridge": True, "few_shot": True, "documents": False},
    )

    assert payload.prompt_structure == "anthropic"
    assert payload.factors.course_bridge is True


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
