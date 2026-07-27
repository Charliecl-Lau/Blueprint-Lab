from copy import deepcopy

from backend.services.assessment_recovery import recover_assessment_payload


def _payload():
    return {
        "questions": [
            {
                "type": "short_answer",
                "metadata": {
                    "question_title": "Component fractions",
                    "question_type": "short_answer",
                    "difficulty_level": "introductory",
                    "intended_assessment_setting": "Quiz",
                    "mse202_concepts": ["Mixtures"],
                    "mse302_concepts": ["Solutions"],
                    "concept_map_bridge": "Not Provided",
                    "materials_science_context": "Alloy solution.",
                    "estimated_time": "10 minutes",
                    "learning_objectives": ["Compare component fractions."],
                },
                "body": "Compare x_A with y_B and select the correct option.",
                "options": [
                    {"body": "x_B is larger.", "is_correct": True},
                ],
                "model_answer": "The fractions x_A and y_B are explicit.",
                "equations": [],
                "revision_options": ["Add data.", "Explain assumptions."],
            }
        ]
    }


def test_recovers_component_symbols_in_question_option_and_solution():
    result = recover_assessment_payload(_payload(), expected_questions=1)

    assert result.strictly_valid is True
    assert result.issues == []
    question = result.parsed_json["questions"][0]
    assert question["body"] == (
        "Compare [[EQ:auto_q1_body_x_a_1]] with [[EQ:auto_q1_body_y_b_1]] "
        "and select the correct option."
    )
    assert question["options"][0]["body"] == "[[EQ:auto_q1_options_0_body_x_b_1]] is larger."
    assert question["model_answer"] == (
        "The fractions [[EQ:auto_q1_model_answer_x_a_1]] and "
        "[[EQ:auto_q1_model_answer_y_b_1]] are explicit."
    )
    expressions = {item["expression"] for item in question["equations"]}
    assert expressions == {"x_a", "x_b", "y_b"}
    assert {item["canonical"] for item in result.actions} == {"x_a", "x_b", "y_b"}


def test_recovery_does_not_guess_bare_component_identity():
    payload = _payload()
    payload["questions"][0]["body"] = "Compare x with y."
    payload["questions"][0]["options"][0]["body"] = "Select the larger value."
    payload["questions"][0]["model_answer"] = "Compare the two variables."

    result = recover_assessment_payload(payload, expected_questions=1)

    assert result.strictly_valid is True
    assert result.actions == []
    assert result.parsed_json["questions"][0]["body"] == "Compare x with y."


def test_recovery_is_idempotent_and_ignores_existing_references():
    once = recover_assessment_payload(_payload(), expected_questions=1)
    twice = recover_assessment_payload(deepcopy(once.parsed_json), expected_questions=1)

    assert twice.strictly_valid is True
    assert twice.actions == []
    assert twice.parsed_json == once.parsed_json


def test_structurally_renderable_but_unrecoverable_response_has_warnings():
    payload = _payload()
    payload["questions"][0]["body"] = "Use G = H - T S."

    result = recover_assessment_payload(payload, expected_questions=1)

    assert result.strictly_valid is False
    assert result.structurally_renderable is True
    assert result.parsed_json is not None
    assert result.issues


def test_invalid_structure_cannot_be_recovered():
    result = recover_assessment_payload({"questions": []}, expected_questions=1)

    assert result.strictly_valid is False
    assert result.structurally_renderable is False
    assert result.parsed_json is None
