import pytest
from pydantic import ValidationError

from backend.schemas.experiment_schema import ExperimentCreate, PromptFactors


@pytest.fixture
def valid_payload():
    return {
        "course": "ENGR 101",
        "topic": "Statics",
        "learning_objectives": "Resolve forces.",
        "assessment_type": "mixed",
        "difficulty": "introductory",
        "number_of_questions": 4,
        "factors": {
            "concept_bridge": False,
            "few_shot": False,
            "reference_content": False,
            "reasoning_guidance": False,
        },
        "factor_inputs": {},
    }


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
    assert payload.cognitive_demand == "remember_understand"
    assert payload.additional_instruction is None
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


@pytest.mark.parametrize("field", ["course", "topic", "learning_objectives"])
def test_assessment_text_fields_reject_whitespace(field, valid_payload):
    valid_payload[field] = "   "

    with pytest.raises(ValidationError):
        ExperimentCreate(**valid_payload)


def test_assessment_text_fields_are_trimmed(valid_payload):
    valid_payload["course"] = "  ENGR 101  "
    valid_payload["topic"] = "  Statics  "
    payload = ExperimentCreate(**valid_payload)

    assert payload.course == "ENGR 101"
    assert payload.topic == "Statics"


def test_enabled_reference_content_uses_pdf_metadata_instead_of_text(valid_payload):
    valid_payload["factors"]["reference_content"] = True
    valid_payload["factor_inputs"].pop("reference_content", None)

    payload = ExperimentCreate(**valid_payload)

    assert payload.factors.reference_content is True
    assert payload.factor_inputs.reference_content is None


def test_assessment_detail_defaults_and_normalization(valid_payload):
    payload = ExperimentCreate(**valid_payload, additional_instruction="   ")

    assert payload.cognitive_demand == "remember_understand"
    assert payload.additional_instruction is None


@pytest.mark.parametrize(
    "value", ["remember_understand", "apply_analyze", "evaluate_create"]
)
def test_experiment_create_accepts_supported_cognitive_demand(valid_payload, value):
    payload = ExperimentCreate(**valid_payload, cognitive_demand=value)

    assert payload.cognitive_demand == value


def test_experiment_create_rejects_unknown_cognitive_demand(valid_payload):
    with pytest.raises(ValidationError):
        ExperimentCreate(**valid_payload, cognitive_demand="evaluate_apply")


def test_additional_instruction_is_trimmed_and_limited(valid_payload):
    payload = ExperimentCreate(
        **valid_payload,
        additional_instruction=f"  {'x' * 20000}  ",
    )

    assert payload.additional_instruction == "x" * 20000

    with pytest.raises(ValidationError):
        ExperimentCreate(**valid_payload, additional_instruction="x" * 20001)
