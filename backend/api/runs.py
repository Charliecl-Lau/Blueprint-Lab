import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from backend.config import settings
from backend.database import SessionLocal, get_db
from backend.models.run import Run
from backend.schemas.run_schema import (
    RecentRun,
    RunCreate,
    RunSummary,
    token_usage_detail,
)
from backend.services.run_service import create_run, retry_run
from backend.workers.assessment_worker import run_generation_pipeline

router = APIRouter(tags=["runs"])
_TERMINAL_RUN_STATES = {"complete", "error"}

def run_detail(run: Run, include_raw_response: bool = False):
    prompt = None
    if run.prompt:
        prompt = {
            "prompt_structure": run.prompt.prompt_structure,
            "actual_prompt_hash": run.prompt.actual_prompt_hash,
            "structure_prompt_version": run.prompt.structure_prompt_version,
            "actual_prompt_generator_version": run.prompt.actual_prompt_generator_version,
            "structure_request_id": run.prompt.structure_request_id,
            "structure_model": run.prompt.structure_model,
            "structure_model_version": run.prompt.structure_model_version,
            "structure_finish_reason": run.prompt.structure_finish_reason,
            "structure_duration_ms": run.prompt.structure_duration_ms,
            "generation_envelope_hash": run.prompt.generation_envelope_hash,
            "generation_request_id": run.request_id,
            "generation_model": run.model,
            "generation_model_version": run.version,
            "generation_finish_reason": run.finish_reason,
            "generation_duration_ms": run.duration_ms,
        }
        if include_raw_response:
            prompt.update({
                "structure_system_prompt": run.prompt.structure_system_prompt,
                "structure_input": run.prompt.structure_input,
                "actual_prompt": run.prompt.actual_prompt,
                "generation_context": run.prompt.generation_context,
            })
    return {
        "id": run.id,
        "run_id": run.id,
        "experiment_id": run.experiment_id,
        "condition_id": run.condition_id,
        "run_number": run.run_number,
        "status": run.status,
        "model_settings": run.model_settings,
        "prompt": prompt,
        "assessment": None if not run.assessment else {
            "parsed_json": run.assessment.parsed_json,
            "output_hash": run.assessment.output_hash,
            "schema_version": run.assessment.schema_version,
            **({"raw_response_text": run.assessment.raw_response_text}
               if include_raw_response else {}),
        },
        "sources": [
            {
                "source_document_id": item.source_document_id,
                "role": item.role,
                "ordinal": item.ordinal,
                "included_text_hash": item.included_text_hash,
                "name": item.source_document.name,
                "version": item.source_document.version,
            }
            for item in run.source_documents
        ],
        "error": None if not run.error_type and not run.error_message else {
            "type": run.error_type,
            "message": run.error_message,
        },
        "artifact_available": run.document_artifact is not None,
        "token_usage": token_usage_detail(run),
    }


def _persisted_run_snapshot(run_id: int, session_factory):
    db = session_factory()
    try:
        run = db.get(Run, run_id)
        if run is None:
            return None
        return {"type": "run_detail", **run_detail(run)}
    finally:
        db.close()


async def _stream_run_progress(run_id: int, session_factory, redis_factory):
    snapshot = _persisted_run_snapshot(run_id, session_factory)
    if snapshot is None:
        return
    yield {"data": json.dumps(snapshot)}
    if snapshot["status"] in _TERMINAL_RUN_STATES:
        return

    async_redis = redis_factory()
    pubsub = async_redis.pubsub()
    channel = f"run:{run_id}:progress"
    try:
        await pubsub.subscribe(channel)
        subscribed_snapshot = _persisted_run_snapshot(run_id, session_factory)
        if subscribed_snapshot is None:
            return
        if subscribed_snapshot != snapshot:
            yield {"data": json.dumps(subscribed_snapshot)}
        if subscribed_snapshot["status"] in _TERMINAL_RUN_STATES:
            return

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            current = _persisted_run_snapshot(run_id, session_factory)
            if current is None:
                return
            yield {"data": json.dumps(current)}
            if current["status"] in _TERMINAL_RUN_STATES:
                return
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await async_redis.aclose()

@router.post("/conditions/{condition_id}/runs", response_model=RunSummary)
def post_run(condition_id: int, payload: RunCreate, db: Session = Depends(get_db)):
    run = create_run(db, condition_id, payload.source_bindings, payload.model_settings)
    run_generation_pipeline.delay(run.id)
    return run


@router.get("/runs/recent", response_model=list[RecentRun])
def get_recent_runs(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    runs = db.scalars(
        select(Run).order_by(Run.created_at.desc(), Run.id.desc()).limit(limit)
    ).all()
    return [
        {
            "id": run.id,
            "experiment_id": run.experiment_id,
            "condition_id": run.condition_id,
            "run_number": run.run_number,
            "status": run.status,
            "topic": run.experiment.topic,
            "condition_label": run.condition.condition_label,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
            "token_usage": token_usage_detail(run),
        }
        for run in runs
    ]


@router.get("/runs/{run_id}/progress")
def get_run_progress(run_id: int, db: Session = Depends(get_db)):
    if db.get(Run, run_id) is None:
        raise HTTPException(404, "Run not found")
    return EventSourceResponse(
        _stream_run_progress(
            run_id,
            SessionLocal,
            lambda: aioredis.from_url(settings.redis_url, decode_responses=True),
        )
    )

@router.get("/runs/{run_id}")
def get_run(run_id: int, include_raw_response: bool = False, db: Session = Depends(get_db)):
    """Return run provenance; raw model output is opt-in research retrieval for this single-user deployment."""
    run = db.get(Run, run_id)
    if run is None: raise HTTPException(404, "Run not found")
    return run_detail(run, include_raw_response)

@router.post("/runs/{run_id}/retry", response_model=RunSummary)
def post_retry(run_id: int, db: Session = Depends(get_db)):
    run = retry_run(db, run_id); run_generation_pipeline.delay(run.id); return run

@router.get("/runs/{run_id}/export-docx")
def export_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None: raise HTTPException(404, "Run not found")
    artifact = run.document_artifact
    if artifact is None: raise HTTPException(404, "DOCX artifact not found")
    return Response(content=artifact.content, media_type=artifact.media_type, headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'})
