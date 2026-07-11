from backend.models import Assessment, Condition, Experiment, Prompt, Run


def test_immutable_research_run_round_trip(test_db):
    experiment = Experiment(
        name="Statics prompt study",
        description="Compare prompt configurations.",
        topic_area="Engineering mechanics",
        research_question="Which prompt produces the clearest assessment?",
        status="active",
        course="ENGR 101",
        topic="Free-body diagrams",
        learning_objectives="Apply equilibrium equations.",
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
        reference_content_enabled=False,
        reasoning_guidance_enabled=False,
        bloom_level_enabled=False,
        factor_configuration={"concept_bridge": "Vectors"},
        factor_inputs={"concept_bridge": "Vectors"},
        condition_label="Concept bridge only",
    )
    run = Run(experiment=experiment, condition=condition, run_number=1, status="completed")
    run.prompt = Prompt(
        prompt_structure="openai",
        system_prompt="You are an assessment designer.",
        final_prompt="Generate three questions.",
        template_version="1.0",
        generator_version="1.0",
        prompt_hash="a" * 64,
    )
    run.assessment = Assessment(
        raw_response_text='{"questions": []}',
        parsed_json={"questions": []},
        output_hash="b" * 64,
        schema_version="1.0",
    )
    test_db.add(experiment)
    test_db.commit()

    saved = test_db.get(Run, run.id)
    assert saved.condition.condition_code == "C100"
    assert saved.prompt.final_prompt == "Generate three questions."
    assert saved.assessment.parsed_json == {"questions": []}
