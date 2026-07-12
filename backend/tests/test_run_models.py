import pytest
from sqlalchemy.exc import IntegrityError

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
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="complete",
        provider="google",
        model_name="gemini-2.0-flash",
    )
    run.prompt = Prompt(
        prompt_structure="openai",
        structure_system_prompt="You are an assessment designer.",
        structure_input="Build an assessment prompt.",
        actual_prompt="Generate three questions.",
        actual_prompt_hash="a" * 64,
        structure_prompt_version="1.0",
        actual_prompt_generator_version="2.0",
        structure_request_id="structure-request-1",
        structure_model="gemini-2.0-flash",
        structure_model_version="2026-07-01",
        structure_finish_reason="stop",
        structure_duration_ms=123,
        generation_context="Use the supplied course evidence.",
        generation_envelope_hash="c" * 64,
    )
    run.assessment = Assessment(
        raw_response_text='{"questions": []}',
        parsed_json={"questions": []},
        output_hash="b" * 64,
        schema_version="1.0",
    )
    test_db.add(experiment)
    test_db.flush()
    run_id = run.id
    test_db.expire_all()

    saved = test_db.get(Run, run_id)
    assert saved.condition.condition_code == "C100"
    assert saved.prompt.structure_system_prompt == "You are an assessment designer."
    assert saved.prompt.structure_input == "Build an assessment prompt."
    assert saved.prompt.actual_prompt == "Generate three questions."
    assert saved.prompt.actual_prompt_hash == "a" * 64
    assert saved.prompt.structure_prompt_version == "1.0"
    assert saved.prompt.actual_prompt_generator_version == "2.0"
    assert saved.prompt.structure_request_id == "structure-request-1"
    assert saved.prompt.structure_model == "gemini-2.0-flash"
    assert saved.prompt.structure_model_version == "2026-07-01"
    assert saved.prompt.structure_finish_reason == "stop"
    assert saved.prompt.structure_duration_ms == 123
    assert saved.prompt.generation_context == "Use the supplied course evidence."
    assert saved.prompt.generation_envelope_hash == "c" * 64
    assert saved.assessment.parsed_json == {"questions": []}
    assert saved.provider == "google"
    assert saved.model == "gemini-2.0-flash"


def test_prompt_hash_rejects_non_sha256_length(test_db):
    experiment = Experiment(
        name="Hash validation",
        description="Validate evidence hashes.",
        topic_area="Testing",
        research_question="Are malformed hashes rejected?",
        status="draft",
        course="ENGR 101",
        topic="Hashes",
        learning_objectives="Validate provenance.",
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=1,
    )
    condition = Condition(
        experiment=experiment,
        condition_code="C100",
        prompt_structure="openai",
        condition_label="Baseline",
    )
    run = Run(experiment=experiment, condition=condition, run_number=1)
    run.prompt = Prompt(
        prompt_structure="openai",
        structure_system_prompt="structure",
        structure_input="input",
        actual_prompt="Generate one question.",
        actual_prompt_hash="too-short",
        structure_prompt_version="1",
        actual_prompt_generator_version="1",
        generation_envelope_hash="a" * 64,
    )
    test_db.add(experiment)

    with pytest.raises(IntegrityError):
        test_db.commit()
