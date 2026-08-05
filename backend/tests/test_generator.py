import json

import pytest

from backend.services.generator import generate_questions


def complete_flat_payload(expression: str) -> dict:
    return {
        "assessment_metadata": {
            "question_title": "Equation rendering assessment",
            "course": "MSE302 Thermodynamics II",
            "topic": "Composition notation",
            "question_type": "short_answer",
            "number_of_questions": 1,
            "difficulty_level": "introductory",
            "cognitive_demand": "Apply/Analyze",
            "intended_assessment_setting": "Instructor question bank",
            "mse202_concepts": ["composition"],
            "mse302_concepts": ["thermodynamics"],
            "concept_map_bridge": "Relate composition notation to thermodynamics.",
            "materials_science_context": "Binary alloy composition.",
            "numerical_computation": "No numerical computation required",
            "estimated_time": "10 minutes",
            "learning_objectives": ["Interpret a materials-science equation."],
            "prompt_design_factors": [],
            "additional_instructions": None,
        },
        "questions": [{
            "type": "short_answer",
            "metadata": {
                "question_title": "Equation rendering",
                "question_type": "short_answer",
                "difficulty_level": "introductory",
                "mse202_concepts": ["composition"],
                "mse302_concepts": ["thermodynamics"],
                "concept_map_bridge": (
                    "Relate composition notation to thermodynamics."
                ),
                "materials_science_context": "Binary alloy composition.",
                "estimated_time_minutes": 10,
                "learning_objectives": [
                    "Interpret a materials-science equation."
                ],
            },
            "body": "Interpret [[EQ:relation]].",
            "options": [],
            "model_answer": "The expression defines the relation.",
            "equations": [{
                "label": "relation",
                "expression": expression,
                "location": "question",
            }],
            "quality_checks": [{
                "criterion": "Correctness",
                "rating": 5,
                "comment": "The notation is preserved.",
            }],
            "revision_options": [
                "Add numerical values.",
                "Ask for physical interpretation.",
            ],
        }]
    }


@pytest.mark.parametrize(
    "expression,expected_type",
    [
        ("x_A", "subscript"),
        ("x_B", "subscript"),
        ("x_A^2", "superscript"),
        ("DeltaH/(T DeltaS)", "fraction"),
        ("sqrt(x_A)", "radical"),
        ("K^-1", "superscript"),
    ],
)
def test_generate_questions_normalizes_linear_equations(
    expression,
    expected_type,
):
    result = generate_questions(
        json.dumps(complete_flat_payload(expression))
    )
    equation = result.questions[0].equations[0]

    assert equation.expression == expression
    assert equation.math.type == expected_type


def test_generate_questions_preserves_combined_subscript_and_superscript():
    result = generate_questions(
        json.dumps(complete_flat_payload("x_A^2"))
    )

    math = result.questions[0].equations[0].math
    assert math.type == "superscript"
    assert math.base.type == "subscript"
    assert math.base.subscript.name == "A"
    assert math.superscript.value == "2"


def test_generate_questions_preserves_signed_superscript():
    result = generate_questions(
        json.dumps(complete_flat_payload("K^-1"))
    )

    superscript = result.questions[0].equations[0].math.superscript
    assert superscript.type == "sequence"
    assert superscript.items[0].type == "operator"
    assert superscript.items[0].value == "-"
    assert superscript.items[1].type == "number"
    assert superscript.items[1].value == "1"


def test_generate_questions_rejects_requested_count_mismatch():
    with pytest.raises(ValueError, match="expected 2 questions, received 1"):
        generate_questions(
            json.dumps(complete_flat_payload("x_A")),
            expected_questions=2,
        )
