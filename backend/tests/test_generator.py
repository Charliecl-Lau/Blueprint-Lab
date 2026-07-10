from unittest.mock import MagicMock

from backend.services.generator import generate_questions


def test_generate_questions_uses_full_prompt_and_rich_schema_directly():
    llm = MagicMock()
    llm.generate_json.return_value = {
        "questions": [{
            "type": "mcq",
            "metadata": {
                "question_title": "Stress definition",
                "mse202_concepts": ["stress"],
                "mse302_concepts": ["mechanical work"],
                "concept_map_bridge": "Relate force intensity to mechanical work.",
                "materials_science_context": "Mechanics of materials.",
                "learning_objectives": ["Define engineering stress."],
            },
            "body": "What is stress?",
            "options": [
                {"body": "Force per area", "is_correct": True},
                {"body": "Force times area", "is_correct": False},
                {"body": "Mass per volume", "is_correct": False},
                {"body": "Velocity over time", "is_correct": False},
            ],
            "model_answer": None,
            "equations": [{"label": "Stress", "expression": "sigma = F/A", "location": "solution"}],
            "quality_check": [{"criterion": "Correctness", "rating": 5, "comment": "Correct."}],
            "revision_options": ["Make it computational."],
        }]
    }

    result = generate_questions(llm=llm, generated_prompt="<context>Generate an assessment.</context>")

    assert result.questions[0].metadata.question_title == "Stress definition"
    assert result.questions[0].equations[0].expression == "sigma = F/A"
    _, kwargs = llm.generate_json.call_args
    assert kwargs["user_message"] == "<context>Generate an assessment.</context>"
    assert "structured assessment plan" not in kwargs["system_prompt"]
    assert "Do not add, remove, or reinterpret" in kwargs["system_prompt"]
