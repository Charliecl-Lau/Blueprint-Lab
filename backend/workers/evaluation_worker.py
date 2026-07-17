import json

import redis
from sqlalchemy import select

from backend.celery_app import celery_app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import DocumentArtifact, Evaluation, Run
from backend.models.experiment import utc_now
from backend.services.assessment_evaluation import (
    EvaluationValidationError,
    evaluate_question,
)
from backend.services.assessment_rubric import RUBRIC_VERSION
from backend.services.docx_exporter import build_assessment_docx
from backend.services.llm_client import LLMClient
from backend.services.reproducibility import sha256_bytes


redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
_MAX_ERROR_MESSAGE_LENGTH = 1000


def _publish_progress(run: Run) -> None:
    message = json.dumps(
        {
            "run_id": run.id,
            "generation_id": run.id,
            "condition_id": run.condition_id,
            "stage": run.status,
            "message": run.progress_message,
        }
    )
    redis_client.publish(f"experiment:{run.experiment_id}:progress", message)
    redis_client.publish(f"run:{run.id}:progress", message)


def _set_progress(db, run: Run, status: str, message: str) -> None:
    run.status = status
    run.progress_message = message
    db.commit()
    _publish_progress(run)


def _has_finalized_evaluation(db, question_id: int, evaluator_identity: str) -> bool:
    return (
        db.scalar(
            select(Evaluation.id).where(
                Evaluation.question_id == question_id,
                Evaluation.evaluation_type == "llm",
                Evaluation.evaluator_identity == evaluator_identity,
                Evaluation.rubric_version == RUBRIC_VERSION,
                Evaluation.status == "finalized",
            )
        )
        is not None
    )


def _save_artifact(db, run: Run) -> None:
    if run.document_artifact is not None:
        return
    assessment = run.assessment
    if assessment is None or assessment.parsed_json is None:
        raise EvaluationValidationError("saved assessment is unavailable")
    docx_bytes = build_assessment_docx(
        run_id=run.id,
        prompt_id=run.prompt.id,
        condition_code=run.condition.condition_code,
        run_number=run.run_number,
        course=run.experiment.course,
        topic=run.experiment.topic,
        questions=assessment.parsed_json["questions"],
    )
    db.add(
        DocumentArtifact(
            run_id=run.id,
            filename=f"blueprint-lab-run-{run.id}.docx",
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            content=docx_bytes,
            content_hash=sha256_bytes(docx_bytes),
        )
    )
    db.commit()


@celery_app.task
def run_llm_evaluation_pipeline(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run is None or run.assessment is None:
            return

        evaluation_model = settings.llm_evaluation_model or settings.llm_model
        llm = LLMClient(model=evaluation_model)
        questions = sorted(run.assessment.questions, key=lambda item: item.ordinal)
        if not questions:
            raise EvaluationValidationError("saved assessment questions are unavailable")

        run.error_type = None
        run.error_message = None
        run.completed_at = None
        _set_progress(
            db,
            run,
            "evaluating_quality",
            "Preparing generated assessment for evaluation",
        )

        def progress(message: str) -> None:
            _set_progress(db, run, "evaluating_quality", message)

        for question in questions:
            if _has_finalized_evaluation(db, question.id, llm.model):
                continue
            evaluate_question(db, run, question, llm, progress)

        _set_progress(db, run, "saving_results", "Saving Results")
        _save_artifact(db, run)
        run.status = "complete"
        run.progress_message = "Complete"
        run.completed_at = utc_now()
        db.commit()
        _publish_progress(run)
    except Exception as exc:
        db.rollback()
        run = db.get(Run, run_id)
        if run is None:
            return
        run.status = "evaluation_failed"
        run.progress_message = "Assessment quality evaluation failed"
        run.error_type = "evaluation_error"
        run.error_message = str(exc)[:_MAX_ERROR_MESSAGE_LENGTH]
        run.completed_at = None
        db.commit()
        _publish_progress(run)
    finally:
        db.close()
