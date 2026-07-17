import json

import redis
from sqlalchemy import select

from backend.celery_app import celery_app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import Evaluation, Run
from backend.services.assessment_evaluation import (
    EvaluationValidationError,
    evaluate_question,
)
from backend.services.assessment_rubric import RUBRIC_VERSION
from backend.services.llm_client import LLMClient


redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
def _publish_progress(run: Run, message_text: str) -> None:
    message = json.dumps(
        {
            "run_id": run.id,
            "generation_id": run.id,
            "condition_id": run.condition_id,
            "stage": "evaluation",
            "message": message_text,
        }
    )
    redis_client.publish(f"experiment:{run.experiment_id}:progress", message)
    redis_client.publish(f"run:{run.id}:progress", message)


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

@celery_app.task
def run_llm_evaluation_pipeline(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if (
            run is None
            or run.status != "complete"
            or run.assessment is None
            or run.document_artifact is None
        ):
            return

        evaluation_model = settings.llm_evaluation_model or settings.llm_model
        llm = LLMClient(model=evaluation_model)
        questions = sorted(run.assessment.questions, key=lambda item: item.ordinal)
        if not questions:
            raise EvaluationValidationError("saved assessment questions are unavailable")

        def progress(message: str) -> None:
            _publish_progress(run, message)

        for question in questions:
            if _has_finalized_evaluation(db, question.id, llm.model):
                continue
            evaluate_question(db, run, question, llm, progress)

        _publish_progress(run, "LLM evaluation complete")
    except Exception:
        db.rollback()
        run = db.get(Run, run_id)
        if run is None:
            return
        _publish_progress(run, "LLM evaluation failed")
    finally:
        db.close()
