import json
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from backend.config import settings
from backend.database import SessionLocal, get_db
from backend.models.run import Run
from backend.models.experiment import utc_now
from backend.services.assessment_recovery_service import (
    AssessmentRecoveryError,
    accept_assessment_defects,
    assessment_is_accepted_or_valid,
    recover_saved_assessment,
    set_warning_run_state,
)
from backend.services.document_artifact import save_assessment_artifact
from backend.services.assessment_rubric import RUBRIC_VERSION
from backend.schemas.run_schema import (
    RecentRun,
    RunCreate,
    RunHistoryDetail,
    RunSummary,
    TerminalRunSummary,
    token_usage_detail,
)
from backend.services.run_history import (
    RunHistoryError,
    get_run_history,
    list_terminal_run_summaries,
)
from backend.services.run_service import (
    create_run,
    mark_generation_dispatch_failed,
    retry_run,
)
from backend.services.llm_client import LLMClient
from backend.services.reference_pdfs import (
    ProviderFileAttachment,
    ReferencePdfValidationError,
    delete_provider_attachments,
    read_reference_pdfs,
    upload_provider_attachments,
)
from backend.workers.assessment_worker import run_generation_pipeline
from backend.workers.evaluation_worker import run_llm_evaluation_pipeline

router = APIRouter(tags=["runs"])
_TERMINAL_RUN_STATES = {"complete", "complete_with_warnings", "error"}


def _locked_run(db: Session, run_id: int) -> Optional[Run]:
    statement = select(Run).where(Run.id == run_id)
    if db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    return db.scalar(statement)


def _ordered_questions(run: Run):
    if run.assessment is None:
        return []
    return sorted(run.assessment.questions, key=lambda item: (item.ordinal, item.id))


def _has_current_llm_evaluation(question) -> bool:
    evaluator_identity = settings.llm_evaluation_model or settings.llm_model
    return any(
        evaluation.evaluation_type == "llm"
        and evaluation.evaluator_identity == evaluator_identity
        and evaluation.rubric_version == RUBRIC_VERSION
        and evaluation.status == "finalized"
        for evaluation in question.evaluations
    )


def _current_llm_evaluations(question):
    evaluator_identity = settings.llm_evaluation_model or settings.llm_model
    return [
        evaluation
        for evaluation in question.evaluations
        if evaluation.evaluation_type == "llm"
        and evaluation.evaluator_identity == evaluator_identity
        and evaluation.rubric_version == RUBRIC_VERSION
    ]


def _evaluation_status(questions) -> str:
    if not questions:
        return "not_started"
    if all(_has_current_llm_evaluation(question) for question in questions):
        return "complete"

    latest_incomplete = []
    has_finalized = False
    for question in questions:
        evaluations = _current_llm_evaluations(question)
        has_finalized = has_finalized or any(
            item.status == "finalized" for item in evaluations
        )
        incomplete = [
            item for item in evaluations if item.status != "finalized"
        ]
        if incomplete:
            latest_incomplete.append(
                max(incomplete, key=lambda item: (item.attempt, item.id or 0))
            )

    if any(item.status in {"draft", "reopened"} for item in latest_incomplete):
        return "in_progress"
    if any(item.status == "failed" for item in latest_incomplete):
        return "failed"
    return "in_progress" if has_finalized else "not_started"


def _grading_question_id(run: Run, reviewer_id: str):
    questions = _ordered_questions(run)
    if not questions:
        return None
    for question in questions:
        reviewed = any(
            evaluation.evaluation_type == "human"
            and evaluation.evaluator_identity == reviewer_id
            and evaluation.status == "finalized"
            for evaluation in question.evaluations
        )
        if not reviewed:
            return question.id
    return questions[0].id

def run_detail(run: Run, include_raw_response: bool = False):
    questions = _ordered_questions(run)
    grading_available = bool(questions) and assessment_is_accepted_or_valid(run) and all(
        _has_current_llm_evaluation(question) for question in questions
    )
    viewer_ready_at = run.viewer_ready_at
    if (
        viewer_ready_at is None
        and run.status in {"complete", "complete_with_warnings"}
        and run.assessment is not None
        and run.assessment.parsed_json is not None
    ):
        viewer_ready_at = run.completed_at or run.created_at
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
                "execution_system_prompt": run.prompt.execution_system_prompt,
                "execution_user_message": run.prompt.execution_user_message,
                "execution_schema_version": run.prompt.execution_schema_version,
            })
    return {
        "id": run.id,
        "run_id": run.id,
        "experiment_id": run.experiment_id,
        "condition_id": run.condition_id,
        "run_number": run.run_number,
        "status": run.status,
        "viewer_ready_at": viewer_ready_at,
        "progress_message": run.progress_message,
        "viewer_available": bool(
            run.assessment
            and run.assessment.parsed_json is not None
            and run.status in {"complete", "complete_with_warnings"}
        ),
        "evaluation_status": _evaluation_status(questions),
        "grading_available": grading_available,
        "grading_question_id": (
            _grading_question_id(run, settings.local_reviewer_id)
            if grading_available
            else None
        ),
        "model_settings": run.model_settings,
        "reference_pdf_filenames": run.reference_pdf_filenames,
        "prompt": prompt,
        "assessment": None if not run.assessment else {
            "id": run.assessment.id,
            "question_ids": [question.id for question in questions],
            "parsed_json": run.assessment.parsed_json,
            "output_hash": run.assessment.output_hash,
            "schema_version": run.assessment.schema_version,
            "validation": {
                "status": run.assessment.validation_status,
                "issues": list(run.assessment.validation_issues or []),
                "recovery_actions": list(run.assessment.recovery_actions or []),
                "parsed_json_hash": run.assessment.parsed_json_hash,
                "defects_accepted_at": (
                    run.assessment.defects_accepted_at.isoformat()
                    if run.assessment.defects_accepted_at else None
                ),
                "defects_accepted_by": run.assessment.defects_accepted_by,
                "acceptance_required": (
                    run.assessment.validation_status == "warning"
                    and run.assessment.defects_accepted_at is None
                ),
            },
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
    try:
        run_generation_pipeline.delay(run.id)
    except Exception as exc:
        mark_generation_dispatch_failed(db, run)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "generation_dispatch_failed",
                "message": "Assessment generation could not be queued. Retry the run.",
            },
        ) from exc
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
            "reference_pdf_filenames": run.reference_pdf_filenames,
            "token_usage": token_usage_detail(run),
        }
        for run in runs
    ]


@router.get("/runs/history/recent", response_model=list[TerminalRunSummary])
def get_terminal_run_history(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    return list_terminal_run_summaries(db, limit)


@router.get("/runs/{run_id}/history", response_model=RunHistoryDetail)
def get_run_history_detail(run_id: int, db: Session = Depends(get_db)):
    try:
        return get_run_history(db, run_id)
    except RunHistoryError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


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


@router.post("/runs/{run_id}/recover-assessment")
def recover_assessment(run_id: int, db: Session = Depends(get_db)):
    run = _locked_run(db, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    if run.status in {"complete", "complete_with_warnings"}:
        return run_detail(run)
    if run.status != "error" or run.error_type != "assessment_parse_error":
        raise HTTPException(409, "Run is not eligible for assessment recovery")
    try:
        state = recover_saved_assessment(db, run, source="manual_recovery")
        if state == "valid":
            run.status = "documenting"
            run.progress_message = "Creating assessment document"
            save_assessment_artifact(db, run)
            run.status = "complete"
            run.progress_message = "Complete"
            run.viewer_ready_at = utc_now()
            run.completed_at = utc_now()
            run.error_type = None
            run.error_message = None
        elif state == "warning":
            set_warning_run_state(run)
        db.commit()
    except AssessmentRecoveryError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    if state == "valid":
        run_llm_evaluation_pipeline.delay(run.id)
    return run_detail(run)


@router.post("/runs/{run_id}/accept-assessment-defects")
def accept_defects(run_id: int, db: Session = Depends(get_db)):
    run = _locked_run(db, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    already_accepted = bool(
        run.assessment and run.assessment.defects_accepted_at is not None
    )
    try:
        accept_assessment_defects(db, run, settings.local_reviewer_id)
        if run.document_artifact is None:
            save_assessment_artifact(db, run)
        db.commit()
    except AssessmentRecoveryError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    if not already_accepted:
        run_llm_evaluation_pipeline.delay(run.id)
    return run_detail(run)

@router.post("/runs/{run_id}/retry", response_model=RunSummary)
async def post_retry(
    run_id: int,
    reference_pdfs: Optional[list[UploadFile]] = File(default=None),
    db: Session = Depends(get_db),
):
    original = db.get(Run, run_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Run not found")
    uploads = list(reference_pdfs or [])
    if not original.reference_pdfs:
        run = retry_run(
            db,
            run_id,
            [upload.filename or "" for upload in uploads] if uploads else None,
        )
        try:
            run_generation_pipeline.delay(run.id)
        except Exception as exc:
            mark_generation_dispatch_failed(db, run)
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "generation_dispatch_failed",
                    "message": "Assessment generation could not be queued. Retry the run.",
                },
            ) from exc
        return run
    if not uploads:
        retry_run(db, run_id)
        raise RuntimeError("unreachable")

    try:
        validated_pdfs = await read_reference_pdfs(uploads)
    except ReferencePdfValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    llm = LLMClient()
    attachments: list[ProviderFileAttachment] = []
    try:
        attachments = upload_provider_attachments(llm, validated_pdfs)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "reference_pdf_upload_failed",
                "message": "Reference PDFs could not be prepared for generation.",
            },
        ) from exc

    try:
        run = retry_run(
            db,
            run_id,
            [pdf.filename for pdf in validated_pdfs],
        )
    except Exception:
        delete_provider_attachments(llm, attachments)
        raise
    try:
        run_generation_pipeline.delay(
            run.id,
            [attachment.to_dict() for attachment in attachments],
        )
    except Exception as exc:
        delete_provider_attachments(llm, attachments)
        mark_generation_dispatch_failed(db, run)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "generation_dispatch_failed",
                "message": "Assessment generation could not be queued. Retry the run.",
            },
        ) from exc
    return run


@router.get("/runs/{run_id}/export-docx")
def export_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None: raise HTTPException(404, "Run not found")
    artifact = run.document_artifact
    if artifact is None: raise HTTPException(404, "DOCX artifact not found")
    return Response(content=artifact.content, media_type=artifact.media_type, headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'})
