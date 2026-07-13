from copy import deepcopy

import pytest
from pydantic import ValidationError

from backend.schemas.assessment_schema import (
    ASSESSMENT_PROVIDER_SCHEMA,
    AssessmentGenerationResponse,
)


@pytest.fixture
def complete_payload():
    return {
        "questions": [{
            "type": "short_answer",
            "metadata": {
                "question_title": "Oxygen equilibrium pressure",
                "question_type": "short_answer",
                "difficulty_level": "hard",
                "intended_assessment_setting": "Timed examination",
                "mse202_concepts": ["Gibbs free energy"],
                "mse302_concepts": ["Gas-solid equilibrium"],
                "concept_map_bridge": "Uses free energy to determine phase equilibrium.",
                "materials_science_context": "Connects thermodynamics to phase transformations.",
            },
            "body": "Determine the equilibrium oxygen pressure.",
            "model_answer": "Set the reaction Gibbs free energy to zero.",
            "quality_check": [{
                "criterion": "Technical correctness",
                "rating": 5,
                "comment": "The equilibrium criterion is applied correctly.",
            }],
            "revision_options": [
                "Provide the standard free energy value.",
                "Ask students to interpret the calculated pressure.",
            ],
        }]
    }


@pytest.mark.parametrize("field", [
    "question_title",
    "question_type",
    "difficulty_level",
    "intended_assessment_setting",
    "mse202_concepts",
    "mse302_concepts",
    "concept_map_bridge",
    "materials_science_context",
])
def test_required_metadata_fields_cannot_be_omitted(complete_payload, field):
    payload = deepcopy(complete_payload)
    del payload["questions"][0]["metadata"][field]

    with pytest.raises(ValidationError):
        AssessmentGenerationResponse.model_validate(payload)


@pytest.mark.parametrize("field", ["mse202_concepts", "mse302_concepts"])
def test_concept_lists_cannot_be_empty(complete_payload, field):
    payload = deepcopy(complete_payload)
    payload["questions"][0]["metadata"][field] = []

    with pytest.raises(ValidationError):
        AssessmentGenerationResponse.model_validate(payload)


def test_quality_check_is_required_and_non_empty(complete_payload):
    for value in (None, []):
        payload = deepcopy(complete_payload)
        if value is None:
            del payload["questions"][0]["quality_check"]
        else:
            payload["questions"][0]["quality_check"] = value
        with pytest.raises(ValidationError):
            AssessmentGenerationResponse.model_validate(payload)


@pytest.mark.parametrize("count", [0, 1, 4])
def test_revision_options_require_two_or_three_items(complete_payload, count):
    payload = deepcopy(complete_payload)
    payload["questions"][0]["revision_options"] = ["Revision"] * count

    with pytest.raises(ValidationError):
        AssessmentGenerationResponse.model_validate(payload)


def test_provider_schema_requires_complete_assessment_contract():
    question = ASSESSMENT_PROVIDER_SCHEMA["properties"]["questions"]["items"]
    assert set(question["required"]) >= {
        "type", "body", "metadata", "quality_check", "revision_options"
    }
    metadata = question["properties"]["metadata"]
    assert set(metadata["required"]) >= {
        "question_title",
        "question_type",
        "difficulty_level",
        "intended_assessment_setting",
        "mse202_concepts",
        "mse302_concepts",
        "concept_map_bridge",
        "materials_science_context",
    }
    assert metadata["properties"]["mse202_concepts"]["minItems"] == 1
    assert metadata["properties"]["mse302_concepts"]["minItems"] == 1
    assert question["properties"]["quality_check"]["minItems"] == 1
    assert question["properties"]["revision_options"]["minItems"] == 2
    assert question["properties"]["revision_options"]["maxItems"] == 3
