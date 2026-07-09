import json
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from backend.config import settings
from backend.database import get_db
from backend.models.run import Run, ControlSet
from backend.models.assessment import Assessment
from backend.schemas.run_schemas import RunCreate, RunResponse
from backend.workers.assessment_worker import run_assessment_pipeline

router = APIRouter(prefix="/runs", tags=["runs"])

_TERMINAL_STAGES = {"complete", "error"}


async def _stream_run_progress(run_id: int, total_assessments: int):
    async_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = async_redis.pubsub()
    await pubsub.subscribe(f"run:{run_id}:progress")

    terminal_count = 0

    yield {"data": json.dumps({"run_id": run_id, "type": "run_started"})}

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        data = json.loads(message["data"])
        yield {"data": json.dumps(data)}

        if data.get("stage") in _TERMINAL_STAGES:
            terminal_count += 1
            if terminal_count >= total_assessments:
                break

    await pubsub.unsubscribe(f"run:{run_id}:progress")
    await async_redis.aclose()


@router.post("")
async def create_run(run_data: RunCreate, db: Session = Depends(get_db)):
    run = Run(
        topic=run_data.topic,
        expectations=run_data.expectations,
        mcq_count=run_data.mcq_count,
        long_answer_count=run_data.long_answer_count,
    )
    db.add(run)
    db.flush()

    control_sets = []
    for cs_data in run_data.control_sets:
        cs = ControlSet(
            run_id=run.id,
            personality=cs_data.personality,
            prompt_length=cs_data.prompt_length,
            result_length=cs_data.result_length,
            action_word_count=cs_data.action_word_count,
        )
        db.add(cs)
        control_sets.append(cs)
    db.flush()

    assessments = []
    for framework in run_data.frameworks:
        for cs in control_sets:
            a = Assessment(
                run_id=run.id,
                framework=framework,
                control_set_id=cs.id,
                status="pending",
            )
            db.add(a)
            assessments.append(a)
    db.commit()

    for a in assessments:
        run_assessment_pipeline.delay(a.id)

    return EventSourceResponse(
        _stream_run_progress(run.id, len(assessments))
    )


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
