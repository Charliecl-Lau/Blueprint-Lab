from backend.models import Condition, Experiment, ModelCallUsage, Run


def _run():
    experiment = Experiment(
        course="ENGR 101",
        topic="Statics",
        learning_objectives="Apply equilibrium equations.",
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=3,
    )
    condition = Condition(
        experiment=experiment,
        condition_code="C100",
        prompt_structure="openai",
        condition_label="Baseline",
    )
    return Run(experiment=experiment, condition=condition, run_number=1)


def test_new_run_can_distinguish_zero_usage_from_legacy_missing_usage(test_db):
    new = _run()
    new.input_tokens = 0
    new.output_tokens = 0
    new.total_tokens = 0
    new.model_call_count = 0
    assert new.input_tokens == 0

    legacy = _run()
    legacy.run_number = 2
    assert legacy.input_tokens is None


def test_model_call_usage_keeps_extra_categories_separate(test_db):
    run = _run()
    test_db.add(run.experiment)
    test_db.flush()
    usage = ModelCallUsage(
        call_id="call-1",
        run_id=run.id,
        stage="assessment",
        attempt=1,
        status="response",
        provider_response_id="response-1",
        input_tokens=11,
        output_tokens=7,
        total_tokens=20,
        cached_content_tokens=3,
        reasoning_tokens=2,
        extra_token_counts={"tool_use_prompt_token_count": 1},
    )
    test_db.add(usage)
    test_db.commit()

    assert usage.input_tokens == 11
    assert usage.extra_token_counts == {"tool_use_prompt_token_count": 1}
    assert usage.run is run
