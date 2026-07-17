from backend.models import Condition, Experiment, Run
from backend.services.llm_client import LLMResult, TokenUsage
from backend.services.usage_tracking import record_model_call


def _run(test_db):
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
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        model_call_count=0,
    )
    test_db.add(experiment)
    test_db.commit()
    return run


def result(response_id, input_tokens, output_tokens, total_tokens):
    return LLMResult(
        raw_text="result",
        provider_request_id=response_id,
        model_name="gemini",
        model_version="v1",
        finish_reason="STOP",
        usage=TokenUsage(
            input_tokens,
            output_tokens,
            total_tokens,
            None,
            None,
            {},
        ),
    )


def test_record_model_call_aggregates_two_responses_once(test_db):
    run = _run(test_db)
    record_model_call(
        test_db,
        run=run,
        call_id="a",
        stage="actual_prompt",
        attempt=1,
        result=result("r1", 10, 4, 14),
    )
    record_model_call(
        test_db,
        run=run,
        call_id="b",
        stage="assessment",
        attempt=1,
        result=result("r2", 20, 8, 28),
    )
    record_model_call(
        test_db,
        run=run,
        call_id="b",
        stage="assessment",
        attempt=1,
        result=result("r2", 20, 8, 28),
    )
    test_db.refresh(run)

    assert (
        run.input_tokens,
        run.output_tokens,
        run.total_tokens,
        run.model_call_count,
    ) == (30, 12, 42, 2)


def test_evaluation_usage_updates_run_totals_and_stage_detail(test_db):
    from backend.schemas.run_schema import token_usage_detail

    run = _run(test_db)
    record_model_call(
        test_db,
        run=run,
        call_id="generation",
        stage="assessment",
        attempt=1,
        result=result("generation-response", 20, 8, 28),
    )
    record_model_call(
        test_db,
        run=run,
        call_id="evaluation",
        stage="evaluation",
        attempt=1,
        result=result("evaluation-response", 12, 8, 20),
    )

    detail = token_usage_detail(run)

    assert (run.input_tokens, run.output_tokens, run.total_tokens) == (32, 16, 48)
    assert detail["stages"][-1] == {
        "stage": "evaluation",
        "input_tokens": 12,
        "output_tokens": 8,
        "total_tokens": 20,
        "model_calls": 1,
    }


def test_provider_response_id_deduplicates_a_second_call_id(test_db):
    run = _run(test_db)
    first = record_model_call(
        test_db,
        run=run,
        call_id="a",
        stage="assessment",
        attempt=1,
        result=result("same-response", 10, 4, 14),
    )
    duplicate = record_model_call(
        test_db,
        run=run,
        call_id="b",
        stage="assessment",
        attempt=1,
        result=result("same-response", 10, 4, 14),
    )

    assert duplicate.id == first.id
    assert run.model_call_count == 1
    assert run.total_tokens == 14


def test_failed_call_counts_request_without_inventing_tokens(test_db):
    run = _run(test_db)
    usage = record_model_call(
        test_db,
        run=run,
        call_id="failed",
        stage="assessment",
        attempt=2,
        failed=True,
    )

    assert usage.status == "failed"
    assert usage.total_tokens is None
    assert run.model_call_count == 1


def test_response_without_usage_counts_request_but_keeps_tokens_unchanged(test_db):
    run = _run(test_db)
    without_usage = LLMResult(
        raw_text="result",
        provider_request_id="response-without-usage",
        model_name="gemini",
        model_version="v1",
        finish_reason="STOP",
    )
    usage = record_model_call(
        test_db,
        run=run,
        call_id="no-usage",
        stage="assessment",
        attempt=1,
        result=without_usage,
    )

    assert usage.status == "response_without_usage"
    assert run.model_call_count == 1
    assert run.total_tokens == 0
