from backend.services.generator import generate_questions


def test_generate_questions_uses_full_prompt_and_rich_schema_directly():
    raw_text = """{
        "questions": [{
            "type": "mcq",
                "metadata": {
                    "question_title": "Stress definition",
                    "question_type": "mcq",
                    "difficulty_level": "introductory",
                    "intended_assessment_setting": "In-class quiz",
                    "mse202_concepts": ["stress"],
                "mse302_concepts": ["mechanical work"],
                "concept_map_bridge": "Relate force intensity to mechanical work.",
                "materials_science_context": "Mechanics of materials.",
                "learning_objectives": ["Define engineering stress."]
            },
            "body": "Which expression defines stress as force per area?",
            "body_segments": [
                {"type": "text", "text": "Which expression defines "},
                {"type": "math", "math": {"type": "symbol", "name": "sigma"}},
                {"type": "text", "text": " as force per area?"}
            ],
            "options": [
                {"body": "Force per area", "is_correct": true},
                {"body": "Force times area", "is_correct": false},
                {"body": "Mass per volume", "is_correct": false},
                {"body": "Velocity over time", "is_correct": false}
            ],
            "model_answer": null,
            "equations": [{
                "label": "Stress",
                "math": {
                    "type": "equation",
                    "left": {"type": "symbol", "name": "sigma"},
                    "right": {
                        "type": "fraction",
                        "numerator": {"type": "symbol", "name": "F"},
                        "denominator": {"type": "symbol", "name": "A"}
                    }
                },
                "location": "solution"
            }],
            "quality_check": [{"criterion": "Correctness", "rating": 5, "comment": "Correct."}],
            "revision_options": ["Make it computational.", "Ask for a units check."]
        }]
    }"""

    result = generate_questions(raw_text)

    assert result.questions[0].metadata.question_title == "Stress definition"
    assert result.questions[0].equations[0].math.type == "equation"
    assert result.questions[0].equations[0].math.right.type == "fraction"
    assert result.questions[0].body_segments[1].math.name == "sigma"
