import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from backend.config import settings
from backend.database import get_db
from backend.models.experiment import Experiment
from backend.schemas.experiment_schema import ExperimentCreate, ExperimentResponse
from backend.services.experiment_service import create_experiment_with_run
from backend.workers.assessment_worker import run_generation_pipeline


router = APIRouter(prefix="/experiments", tags=["experiments"])
_TERMINAL_STAGES = {"complete", "generation_failed", "evaluation_failed"}


async def _stream_experiment_progress(experiment_id: int, total_generations: int):
    async_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = async_redis.pubsub()
    channel = f"experiment:{experiment_id}:progress"
    terminal_generation_ids: set[int] = set()
    try:
        await pubsub.subscribe(channel)
        yield {"data": json.dumps({"experiment_id": experiment_id, "type": "experiment_started"})}

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            yield {"data": json.dumps(data)}
            if data.get("stage") in _TERMINAL_STAGES:
                terminal_generation_ids.add(data["generation_id"])
                if len(terminal_generation_ids) >= total_generations:
                    break
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await async_redis.aclose()


@router.post("", response_model=ExperimentResponse)
def create_experiment(
    payload: ExperimentCreate,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=1,
        max_length=64,
    ),
    db: Session = Depends(get_db),
):
    experiment, run, created = create_experiment_with_run(
        db, payload, idempotency_key
    )
    if created:
        run_generation_pipeline.delay(run.id)
    return experiment


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(experiment_id: int, db: Session = Depends(get_db)):
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment


@router.get("/{experiment_id}/progress")
async def experiment_progress(experiment_id: int, db: Session = Depends(get_db)):
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return EventSourceResponse(
        _stream_experiment_progress(experiment.id, len(experiment.generations))
    )
