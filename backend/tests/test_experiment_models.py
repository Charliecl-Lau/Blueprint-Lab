from backend.models import Condition, Experiment


def test_experiment_condition_metadata_round_trip(test_db):
    experiment = Experiment(
        name="Free-body diagram study",
        description="Research prompt factors.",
        topic_area="Statics",
        research_question="Which factors improve alignment?",
        status="active",
        course="ENGR 101",
        topic="Free-body diagrams",
        learning_objectives="Apply equilibrium equations to planar systems.",
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=3,
    )
    condition = Condition(
        experiment=experiment,
        condition_code="C100",
        prompt_structure="openai",
        concept_bridge_enabled=True,
        few_shot_enabled=False,
        reference_content_enabled=True,
        reasoning_guidance_enabled=False,
        bloom_level_enabled=True,
        factor_configuration={"concept_bridge": "Vectors"},
        factor_inputs={"reference_content": "SI units"},
        condition_label="Concept bridge and reference content",
    )
    test_db.add(experiment)
    test_db.commit()

    saved = test_db.get(Condition, condition.id)
    assert saved.experiment.name == "Free-body diagram study"
    assert saved.condition_code == "C100"
    assert saved.factor_configuration == {"concept_bridge": "Vectors"}
