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


def test_quality_check_is_not_required_and_legacy_values_remain_readable(complete_payload):
    without_quality_check = deepcopy(complete_payload)
    del without_quality_check["questions"][0]["quality_check"]

    parsed = AssessmentGenerationResponse.model_validate(without_quality_check)
    legacy = AssessmentGenerationResponse.model_validate(complete_payload)

    assert not hasattr(parsed.questions[0], "quality_check")
    assert not hasattr(legacy.questions[0], "quality_check")


@pytest.mark.parametrize("count", [0, 1, 4])
def test_revision_options_require_two_or_three_items(complete_payload, count):
    payload = deepcopy(complete_payload)
    payload["questions"][0]["revision_options"] = ["Revision"] * count

    with pytest.raises(ValidationError):
        AssessmentGenerationResponse.model_validate(payload)


def test_provider_schema_requires_complete_assessment_contract():
    question = ASSESSMENT_PROVIDER_SCHEMA["properties"]["questions"]["items"]
    assert set(question["required"]) >= {
        "type", "body", "metadata", "equations", "revision_options"
    }
    assert "quality_check" not in question["required"]
    assert "quality_check" not in question["properties"]
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
    assert question["properties"]["revision_options"]["minItems"] == 2
    assert question["properties"]["revision_options"]["maxItems"] == 3


def test_flat_equation_references_accept_question_and_solution_locations(
    complete_payload,
):
    question = complete_payload["questions"][0]
    question["body"] = "Evaluate [[EQ:question_relation]]."
    question["model_answer"] = "Apply [[EQ:solution_relation]]."
    question["equations"] = [
        {
            "label": "question_relation",
            "expression": "G_mix = H_mix - T S_mix",
            "location": "question",
        },
        {
            "label": "solution_relation",
            "expression": "G_mix/(R T) = x_A ln(x_A) + x_B ln(x_B)",
            "location": "solution",
        },
    ]

    parsed = AssessmentGenerationResponse.model_validate(complete_payload)

    assert [item.label for item in parsed.questions[0].equations] == [
        "question_relation",
        "solution_relation",
    ]


def test_flat_equation_references_report_all_cross_location_labels(
    complete_payload,
):
    shared_labels = [
        "g_mix_def",
        "g_mix_res",
        "h_mix_val",
        "s_mix_def",
        "temp",
        "xa_val",
    ]
    question = complete_payload["questions"][0]
    question["body"] = "Use " + " ".join(
        f"[[EQ:{label}]]" for label in shared_labels
    )
    question["model_answer"] = "Apply " + " ".join(
        f"[[EQ:{label}]]" for label in reversed(shared_labels)
    )
    question["equations"] = [
        {
            "label": label,
            "expression": f"{label} = value",
            "location": "question",
        }
        for label in shared_labels
    ]

    with pytest.raises(ValidationError) as exc_info:
        AssessmentGenerationResponse.model_validate(complete_payload)

    assert (
        "equation labels referenced from both question and solution: "
        "g_mix_def, g_mix_res, h_mix_val, s_mix_def, temp, xa_val"
        in str(exc_info.value)
    )


def test_flat_equation_references_reject_duplicate_labels(complete_payload):
    question = complete_payload["questions"][0]
    question["body"] = "Evaluate [[EQ:relation]]."
    question["equations"] = [
        {"label": "relation", "expression": "G = H - T S", "location": "question"},
        {"label": "relation", "expression": "A = B", "location": "question"},
    ]

    with pytest.raises(ValidationError, match="equation labels must be unique"):
        AssessmentGenerationResponse.model_validate(complete_payload)


def test_flat_equation_references_reject_unknown_labels(complete_payload):
    complete_payload["questions"][0]["body"] = "Evaluate [[EQ:missing]]."

    with pytest.raises(ValidationError, match="unknown equation label: missing"):
        AssessmentGenerationResponse.model_validate(complete_payload)


def test_flat_equation_references_reject_unreferenced_entries(complete_payload):
    complete_payload["questions"][0]["equations"] = [{
        "label": "unused",
        "expression": "G = H - T S",
        "location": "question",
    }]

    with pytest.raises(ValidationError, match="equation is not referenced: unused"):
        AssessmentGenerationResponse.model_validate(complete_payload)


def test_flat_equation_references_reject_location_mismatches(complete_payload):
    question = complete_payload["questions"][0]
    question["model_answer"] = "Apply [[EQ:question_relation]]."
    question["equations"] = [{
        "label": "question_relation",
        "expression": "G = H - T S",
        "location": "question",
    }]

    with pytest.raises(
        ValidationError,
        match="question equation referenced from solution: question_relation",
    ):
        AssessmentGenerationResponse.model_validate(complete_payload)


def test_flat_equation_references_reject_formula_text_outside_placeholders(
    complete_payload,
):
    question = complete_payload["questions"][0]
    question["body"] = (
        "The molar enthalpy of mixing is zero, DeltaH_mix = 0. "
        "Use [[EQ:entropy_relation]]."
    )
    question["model_answer"] = "Therefore DeltaG_mix = -T DeltaS_mix."
    question["equations"] = [{
        "label": "entropy_relation",
        "expression": "DeltaS_mix = -R(x_A ln(x_A) + x_B ln(x_B))",
        "location": "question",
    }]

    with pytest.raises(
        ValidationError,
        match="mathematical expression must use an equation reference",
    ):
        AssessmentGenerationResponse.model_validate(complete_payload)


def test_flat_equation_validation_reports_all_offending_fields_and_text(
    complete_payload,
):
    question = complete_payload["questions"][0]
    question["body"] = (
        "Using dH = TdS + VdP, derive the Joule-Thomson coefficient."
    )
    question["model_answer"] = (
        "For an ideal gas, PV = RT and C_p = (partial H/partial T)_P."
    )

    with pytest.raises(ValidationError) as caught:
        AssessmentGenerationResponse.model_validate(complete_payload)

    message = str(caught.value)
    assert "body: mathematical expression must use an equation reference" in message
    assert "dH = TdS + VdP" in message
    assert (
        "model_answer: mathematical expression must use an equation reference"
        in message
    )
    assert "PV = RT" in message
    assert "C_p = (partial H/partial T)_P" in message


def test_flat_equation_references_reject_signed_superscript_text(
    complete_payload,
):
    complete_payload["questions"][0]["body"] = (
        "Report the result using K^-1 as the temperature exponent."
    )

    with pytest.raises(
        ValidationError,
        match="mathematical expression must use an equation reference",
    ):
        AssessmentGenerationResponse.model_validate(complete_payload)


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


def test_structured_math_ast_and_embedded_segments_are_validated(complete_payload):
    question = complete_payload["questions"][0]
    equation = thermodynamic_equation_ast()
    question["body_segments"] = [
        {"type": "text", "text": "Use "},
        {"type": "math", "math": equation},
        {"type": "text", "text": " to calculate the slope."},
    ]
    question["model_answer_segments"] = [
        {"type": "text", "text": "The governing relation is "},
        {"type": "math", "math": equation},
        {"type": "text", "text": "."},
    ]
    question["equations"] = [{
        "label": "Clapeyron equation",
        "math": equation,
        "location": "solution",
    }]

    parsed = AssessmentGenerationResponse.model_validate(complete_payload)

    assert parsed.questions[0].equations[0].math.type == "equation"
    assert parsed.questions[0].body_segments[1].math.right.type == "fraction"


def test_malformed_structured_fraction_is_rejected(complete_payload):
    complete_payload["questions"][0]["body_segments"] = [{
        "type": "math",
        "math": {
            "type": "fraction",
            "numerator": {"type": "symbol", "name": "x"},
        },
    }]

    with pytest.raises(ValidationError):
        AssessmentGenerationResponse.model_validate(complete_payload)


def test_provider_schema_remains_flat_and_does_not_send_recursive_math_to_provider():
    question = ASSESSMENT_PROVIDER_SCHEMA["properties"]["questions"]["items"]
    assert "$defs" not in ASSESSMENT_PROVIDER_SCHEMA
    assert "body_segments" not in question["properties"]
    assert "model_answer_segments" not in question["properties"]
    equation = question["properties"]["equations"]["items"]
    assert equation == {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "expression": {"type": "string"},
            "location": {
                "type": "string",
                "enum": ["question", "solution"],
            },
        },
        "required": ["label", "expression", "location"],
    }
    option = question["properties"]["options"]["items"]
    assert "segments" not in option["properties"]
