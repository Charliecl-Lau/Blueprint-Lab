import json
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from backend.config import settings
from backend.database import get_db
from backend.models.experiment import Experiment
from backend.schemas.experiment_schema import ExperimentCreate, ExperimentResponse
from backend.services.experiment_service import (
    ExperimentValidationError,
    ValidationIssue,
    create_experiment_with_run,
    existing_experiment_graph,
    validate_reference_pdf_filenames,
)
from backend.services.llm_client import LLMClient
from backend.services.reference_pdfs import (
    ProviderFileAttachment,
    ReferencePdfValidationError,
    read_reference_pdfs,
)
from backend.workers.assessment_worker import run_generation_pipeline


router = APIRouter(prefix="/experiments", tags=["experiments"])
_TERMINAL_STAGES = {"complete", "error"}


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


def _reference_pdf_issue(message: str) -> ExperimentValidationError:
    return ExperimentValidationError(
        [
            ValidationIssue(
                section="Prompt Design Factors",
                field="reference_pdfs",
                label="Reference Content PDFs",
                message=message,
            )
        ]
    )


def _delete_provider_files(
    llm: LLMClient, attachments: list[ProviderFileAttachment]
) -> None:
    for attachment in reversed(attachments):
        try:
            llm.delete_file(attachment.name)
        except Exception:
            continue


@router.post("", response_model=ExperimentResponse)
async def create_experiment(
    payload: str = Form(...),
    reference_pdfs: Optional[list[UploadFile]] = File(default=None),
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=1,
        max_length=64,
    ),
    db: Session = Depends(get_db),
):
    try:
        parsed_payload = ExperimentCreate.model_validate_json(payload)
    except ValidationError as exc:
        errors = []
        for error in exc.errors():
            error = dict(error)
            error["loc"] = ("body", *error.get("loc", ()))
            errors.append(error)
        raise RequestValidationError(errors) from exc

    existing = existing_experiment_graph(db, idempotency_key)
    if existing is not None:
        return existing[0]

    uploads = list(reference_pdfs or [])
    validate_reference_pdf_filenames(
        parsed_payload,
        [upload.filename or "" for upload in uploads],
    )
    try:
        validated_pdfs = await read_reference_pdfs(uploads) if uploads else []
    except ReferencePdfValidationError as exc:
        raise _reference_pdf_issue(str(exc)) from exc

    llm = LLMClient() if validated_pdfs else None
    attachments: list[ProviderFileAttachment] = []
    try:
        if llm is not None:
            for pdf in validated_pdfs:
                attachments.append(llm.upload_pdf(pdf))
    except Exception as exc:
        _delete_provider_files(llm, attachments)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "reference_pdf_upload_failed",
                "message": "Reference PDFs could not be prepared for generation.",
            },
        ) from exc

    try:
        experiment, run, created = create_experiment_with_run(
            db,
            parsed_payload,
            idempotency_key,
            [pdf.filename for pdf in validated_pdfs],
        )
        if not created:
            if llm is not None:
                _delete_provider_files(llm, attachments)
            return experiment
        run_generation_pipeline.delay(
            run.id, [attachment.to_dict() for attachment in attachments]
        )
    except Exception:
        if llm is not None:
            _delete_provider_files(llm, attachments)
        raise
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
