import json
from copy import deepcopy
from unittest.mock import MagicMock, patch

from backend.models import (
    Assessment,
    Condition,
    Evaluation,
    Experiment,
    ModelCallUsage,
    Prompt,
    Run,
)
from backend.models.experiment import utc_now
from backend.services.assessment_evaluation import persist_assessment_questions
from backend.services.llm_client import LLMResult, TokenUsage


QUESTION = {
    "type": "long_answer",
    "metadata": {
        "question_title": "Phase stability",
        "question_type": "long_answer",
        "difficulty_level": "advanced",
        "intended_assessment_setting": "Homework",
        "mse202_concepts": ["Equilibrium"],
        "mse302_concepts": ["Chemical potential"],
        "concept_map_bridge": "Connects equilibrium to chemical potential.",
        "materials_science_context": "Compares phases in an alloy.",
    },
    "body": "Explain which phase is stable.",
    "options": [],
    "model_answer": "The phase with lower Gibbs free energy is stable.",
    "revision_options": ["Add numerical data."],
}


def _evaluation_json(score=5):
    return json.dumps(
        {
            "criteria": [
                {
                    "criterion_key": key,
                    "score": score,
                    "justification": f"Evidence for {key}.",
                    "strengths": ["A strength."],
                    "weaknesses": [],
                    "suggested_improvements": [],
                    "suggested_modifications": [],
                }
                for key in (
                    "technical_correctness",
                    "course_alignment",
                    "blooms_alignment",
                    "clarity_solution",
                    "materials_context",
                )
            ],
            "major_strengths": ["Strong alignment."],
            "major_weaknesses": [],
            "highest_priority_revision": "None required.",
            "recommended_instructor_action": "Accept without revision",
        }
    )


def _result(raw_text=None):
    return LLMResult(
        raw_text=raw_text or _evaluation_json(),
        provider_request_id="evaluation-response",
        model_name="gemini-evaluator",
        model_version="evaluation-v1",
        finish_reason="STOP",
        usage=TokenUsage(12, 8, 20, None, None, {}),
    )


def _saved_run(test_db, *, question_count=1):
    experiment = Experiment(
        course="MSE302",
        topic="Phase stability",
        learning_objectives="Analyze phase stability.",
        assessment_type="long_answer",
        difficulty="advanced",
        number_of_questions=question_count,
    )
    condition = Condition(
        experiment=experiment,
        condition_code="C100",
        prompt_structure="openai",
        factor_configuration={"concept_bridge": True},
        factor_inputs={"concept_bridge": "Equilibrium to chemical potential"},
        condition_label="Concept bridge enabled",
    )
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="evaluating_quality",
        model="gemini-generation",
        version="generation-v1",
        model_settings={},
        input_tokens=20,
        output_tokens=8,
        total_tokens=28,
        model_call_count=1,
        viewer_ready_at=utc_now(),
        progress_message="Preparing generated assessment for evaluation",
    )
    run.model_call_usages.append(
        ModelCallUsage(
            call_id="generation-call",
            stage="assessment",
            attempt=1,
            status="response",
            provider_response_id="generation-response",
            input_tokens=20,
            output_tokens=8,
            total_tokens=28,
            extra_token_counts={},
        )
    )
    run.prompt = Prompt(
        prompt_structure="openai",
        structure_system_prompt="System",
        structure_input="Input",
        actual_prompt="Generate an assessment.",
        actual_prompt_hash="a" * 64,
        structure_prompt_version="template-v1",
        actual_prompt_generator_version="generator-v1",
        generation_context="Context",
        generation_envelope_hash="b" * 64,
    )
    questions = []
    for ordinal in range(question_count):
        item = deepcopy(QUESTION)
        item["body"] = f"{item['body']} Question {ordinal + 1}."
        questions.append(item)
    run.assessment = Assessment(
        raw_response_text=json.dumps({"questions": questions}),
        parsed_json={"questions": questions},
        output_hash="c" * 64,
        schema_version="1",
    )
    test_db.add(experiment)
    test_db.commit()
    persist_assessment_questions(test_db, run.assessment)
    test_db.commit()
    return run


def _run_worker(test_db, llm):
    test_db.close = MagicMock()
    with (
        patch("backend.workers.evaluation_worker.SessionLocal", return_value=test_db),
        patch("backend.workers.evaluation_worker.LLMClient", return_value=llm),
        patch(
            "backend.workers.evaluation_worker.build_assessment_docx",
            return_value=b"PK-evaluation-docx",
        ),
        patch("backend.workers.evaluation_worker.redis_client") as redis_client,
    ):
        from backend.workers.evaluation_worker import run_llm_evaluation_pipeline

        run_llm_evaluation_pipeline.run(llm.run_id)
        return redis_client


def test_evaluation_worker_finalizes_saved_questions_artifact_and_usage(test_db):
    run = _saved_run(test_db)
    before = deepcopy(run.assessment.parsed_json)
    llm = MagicMock(model="gemini-evaluator", run_id=run.id)
    llm.generate.return_value = _result()

    redis_client = _run_worker(test_db, llm)

    test_db.refresh(run)
    assert run.status == "complete"
    assert run.completed_at is not None
    assert run.viewer_ready_at is not None
    assert run.assessment.parsed_json == before
    assert run.document_artifact.content == b"PK-evaluation-docx"
    assert run.total_tokens == 48
    assert [(item.stage, item.total_tokens) for item in run.model_call_usages] == [
        ("assessment", 28),
        ("evaluation", 20),
    ]
    evaluation = test_db.query(Evaluation).filter_by(run_id=run.id).one()
    assert evaluation.status == "finalized"
    published = [call.args[1] for call in redis_client.publish.call_args_list]
    assert any('"stage": "saving_results"' in item for item in published)
    assert any('"stage": "complete"' in item for item in published)


def test_evaluation_failure_preserves_viewer_ready_assessment(test_db):
    run = _saved_run(test_db)
    before = deepcopy(run.assessment.parsed_json)
    ready_at = run.viewer_ready_at
    llm = MagicMock(model="gemini-evaluator", run_id=run.id)
    llm.generate.return_value = _result('{"criteria": []}')

    _run_worker(test_db, llm)

    test_db.refresh(run)
    assert run.status == "evaluation_failed"
    assert run.viewer_ready_at == ready_at
    assert run.assessment.parsed_json == before
    assert run.document_artifact is None
    assert run.error_type == "evaluation_error"
    assert run.total_tokens == 48
    assert run.model_call_usages[-1].stage == "evaluation"
    assert run.model_call_usages[-1].total_tokens == 20
    assert test_db.query(Evaluation).filter_by(run_id=run.id).one().status == "failed"


def test_evaluation_retry_skips_finalized_question_and_fills_missing_question(test_db):
    run = _saved_run(test_db, question_count=2)
    first, second = sorted(run.assessment.questions, key=lambda item: item.ordinal)
    llm = MagicMock(model="gemini-evaluator")
    llm.generate.return_value = _result()
    from backend.services.assessment_evaluation import evaluate_question

    original = evaluate_question(test_db, run, first, llm, lambda message: None)
    original_id = original.id
    llm.generate.reset_mock()
    llm.run_id = run.id

    _run_worker(test_db, llm)

    assert llm.generate.call_count == 1
    assert test_db.get(Evaluation, original_id).status == "finalized"
    assert (
        test_db.query(Evaluation)
        .filter_by(question_id=second.id, status="finalized")
        .count()
        == 1
    )
