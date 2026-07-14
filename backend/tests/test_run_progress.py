import json

import pytest

from backend.api.runs import _stream_run_progress
from backend.models import Condition, Experiment, Run


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
async def test_terminal_snapshot_closes_without_waiting_for_redis(test_db):
    run = _run(test_db, status="complete")
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
    assert json.loads(events[0]["data"])["status"] == "complete"
    assert redis_opened is False
