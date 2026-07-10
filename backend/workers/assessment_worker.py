import json
import time

import redis
from sqlalchemy.orm import Session

from backend.celery_app import celery_app
from backend.config import settings
from backend.database import SessionLocal
from backend.models.experiment import DocumentArtifact, Generation, PromptRecord, utc_now
from backend.schemas.experiment_schema import PromptFactors
from backend.services.docx_exporter import build_assessment_docx
from backend.services.generator import generate_questions
from backend.services.llm_client import LLMClient
from backend.services.prompt_generator import generate_prompt


redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _publish_progress(
    experiment_id: int,
    generation_id: int,
    condition_id: int,
    stage: str,
) -> None:
    redis_client.publish(
        f"experiment:{experiment_id}:progress",
        json.dumps(
            {
                "generation_id": generation_id,
                "condition_id": condition_id,
                "stage": stage,
            }
        ),
    )


def _set_status(db: Session, generation: Generation, status: str) -> None:
    generation.status = status
    db.commit()


def _factors_from_condition(condition) -> PromptFactors:
    return PromptFactors(
        concept_bridge=condition.concept_bridge_enabled,
        few_shot=condition.few_shot_enabled,
        reference_content=condition.reference_content_enabled,
        reasoning_guidance=condition.reasoning_guidance_enabled,
    )


@celery_app.task(bind=True, max_retries=3)
def run_generation_pipeline(self, generation_id: int) -> None:
    db = SessionLocal()
    try:
        generation = db.get(Generation, generation_id)
        if generation is None:
            return

        experiment = generation.experiment
        condition = generation.condition
        try:
            llm = LLMClient()
            started = time.perf_counter()

            _set_status(db, generation, "prompting")
            _publish_progress(experiment.id, generation.id, condition.id, "prompting")
            prompt_text = generate_prompt(
                course=experiment.course,
                topic=experiment.topic,
                learning_objectives=experiment.learning_objectives,
                assessment_type=experiment.assessment_type,
                difficulty=experiment.difficulty,
                number_of_questions=experiment.number_of_questions,
                prompt_structure=condition.prompt_structure,
                factors=_factors_from_condition(condition),
                factor_inputs=condition.factor_inputs,
            )
            prompt_record = PromptRecord(
                generation_id=generation.id,
                prompt_structure=condition.prompt_structure,
                full_prompt=prompt_text,
            )
            db.add(prompt_record)
            db.commit()
            db.refresh(prompt_record)

            _set_status(db, generation, "generating")
            _publish_progress(experiment.id, generation.id, condition.id, "generating")
            generated = generate_questions(llm=llm, generated_prompt=prompt_text)
            generation.generated_json = generated.model_dump()
            generation.model_name = getattr(llm, "model_name", None)
            generation.model_version = getattr(llm, "model_version", None)
            generation.generation_time_ms = int((time.perf_counter() - started) * 1000)
            generation.completed_at = utc_now()
            db.commit()

            _set_status(db, generation, "documenting")
            _publish_progress(experiment.id, generation.id, condition.id, "documenting")
            docx_bytes = build_assessment_docx(
                assessment_id=generation.id,
                prompt_id=prompt_record.id,
                condition_label=condition.condition_label,
                course=experiment.course,
                topic=experiment.topic,
                questions=generation.generated_json["questions"],
            )
            db.add(
                DocumentArtifact(
                    generation_id=generation.id,
                    filename=f"blueprint-lab-generation-{generation.id}.docx",
                    media_type=(
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                    content=docx_bytes,
                )
            )
            db.commit()

            _set_status(db, generation, "complete")
            _publish_progress(experiment.id, generation.id, condition.id, "complete")
        except Exception as exc:
            db.rollback()
            _set_status(db, generation, "error")
            _publish_progress(experiment.id, generation.id, condition.id, "error")
            raise self.retry(exc=exc, countdown=10)
    finally:
        db.close()

