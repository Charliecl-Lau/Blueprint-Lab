import json

import pytest

from backend.api.runs import _stream_run_progress
from backend.config import settings
from backend.api.runs import run_detail
from backend.models import (
    Assessment,
    Condition,
    Evaluation,
    Experiment,
    Run,
)
from backend.services.assessment_evaluation import persist_assessment_questions
from backend.services.assessment_rubric import RUBRIC_SNAPSHOT, RUBRIC_VERSION


def _run(test_db, *, status):
    experiment = Experiment(
        course="C",
        topic="T",
        learning_objectives="L",
        assessment_type="mixed",
        difficulty="D",
        number_of_questions=1,
    )
    condition = Condition(
        experiment=experiment,
        prompt_structure="openai",
        factor_inputs={},
        condition_label="Baseline",
    )
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status=status,
        model_settings={},
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        model_call_count=0,
    )
    test_db.add(experiment)
    test_db.commit()
    return run


class SessionView:
    def __init__(self, run):
        self.run = run
        self.closed = False

    def get(self, model, run_id):
        return self.run if self.run.id == run_id else None

    def close(self):
        self.closed = True


async def first_event(stream):
    event = await stream.__anext__()
    await stream.aclose()
    return event


@pytest.mark.asyncio
async def test_progress_stream_emits_database_snapshot_before_redis(test_db):
    run = _run(test_db, status="generating")
    sessions = []

    def session_factory():
        session = SessionView(run)
        sessions.append(session)
        return session

    def redis_factory():
        raise AssertionError("Redis must not be opened before the database snapshot")

    event = await first_event(
        _stream_run_progress(run.id, session_factory, redis_factory)
    )
    snapshot = json.loads(event["data"])

    assert snapshot["status"] == run.status
    assert snapshot["run_id"] == run.id
    assert snapshot["type"] == "run_detail"
    assert sessions[0].closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", ["complete", "error"]
)
async def test_terminal_snapshot_closes_without_waiting_for_redis(test_db, status):
    run = _run(test_db, status=status)
    redis_opened = False

    def redis_factory():
        nonlocal redis_opened
        redis_opened = True
        raise AssertionError("terminal streams must not open Redis")

    events = [
        event
        async for event in _stream_run_progress(
            run.id,
            lambda: SessionView(run),
            redis_factory,
        )
    ]

    assert len(events) == 1
    assert json.loads(events[0]["data"])["status"] == status
    assert redis_opened is False


def test_run_detail_exposes_viewer_evaluation_and_grading_state(test_db):
    run = _run(test_db, status="complete")
    run.viewer_ready_at = run.created_at
    run.progress_message = "Complete"
    run.assessment = Assessment(
        raw_response_text='{"questions": [{"body": "Saved"}]}',
        parsed_json={"questions": [{"body": "Saved"}]},
        output_hash="a" * 64,
        schema_version="1",
    )
    test_db.commit()
    question = persist_assessment_questions(test_db, run.assessment)[0]
    run.assessment.questions
    test_db.add(
        Evaluation.from_run(
            run,
            question=question,
            evaluation_type="llm",
            evaluator_identity=(
                settings.llm_evaluation_model or settings.llm_model
            ),
            evaluation_model=(settings.llm_evaluation_model or settings.llm_model),
            rubric_version=RUBRIC_VERSION,
            rubric_snapshot=RUBRIC_SNAPSHOT,
        )
    )
    test_db.flush()
    question.evaluations[0].status = "finalized"
    test_db.commit()

    detail = run_detail(run)

    assert detail["viewer_ready_at"] == run.viewer_ready_at
    assert detail["progress_message"] == "Complete"
    assert detail["evaluation_status"] == "complete"
    assert detail["grading_available"] is True
    assert detail["grading_question_id"] == question.id
    assert detail["assessment"]["id"] == run.assessment.id
    assert detail["assessment"]["question_ids"] == [question.id]


def test_generation_failure_is_terminal_without_evaluation_state(test_db):
    run = _run(test_db, status="error")
    test_db.commit()

    detail = run_detail(run)

    assert detail["evaluation_status"] == "not_started"
    assert detail["grading_available"] is False
