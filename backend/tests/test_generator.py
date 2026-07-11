from backend.services.generator import generate_questions


def test_generate_questions_uses_full_prompt_and_rich_schema_directly():
    raw_text = """{
        "questions": [{
            "type": "mcq",
            "metadata": {
                "question_title": "Stress definition",
                "mse202_concepts": ["stress"],
                "mse302_concepts": ["mechanical work"],
                "concept_map_bridge": "Relate force intensity to mechanical work.",
                "materials_science_context": "Mechanics of materials.",
                "learning_objectives": ["Define engineering stress."]
            },
            "body": "What is stress?",
            "options": [
                {"body": "Force per area", "is_correct": true},
                {"body": "Force times area", "is_correct": false},
                {"body": "Mass per volume", "is_correct": false},
                {"body": "Velocity over time", "is_correct": false}
            ],
            "model_answer": null,
            "equations": [{"label": "Stress", "expression": "sigma = F/A", "location": "solution"}],
            "quality_check": [{"criterion": "Correctness", "rating": 5, "comment": "Correct."}],
            "revision_options": ["Make it computational."]
        }]
    }"""

    result = generate_questions(raw_text)

    assert result.questions[0].metadata.question_title == "Stress definition"
    assert result.questions[0].equations[0].expression == "sigma = F/A"
