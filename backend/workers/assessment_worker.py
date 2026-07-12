import json
import time

import redis
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.celery_app import celery_app
from backend.config import settings
from backend.database import SessionLocal
from backend.models.experiment import utc_now
from backend.models.run import Assessment, DocumentArtifact, Prompt, Run
from backend.schemas.experiment_schema import PromptFactors
from backend.services.actual_prompt import (
    ACTUAL_PROMPT_GENERATOR_VERSION,
    ActualPromptValidationError,
    build_structure_input,
    validate_actual_prompt,
)
from backend.services.docx_exporter import build_assessment_docx
from backend.services.generation_context import build_generation_context
from backend.services.generator import generate_questions
from backend.services.llm_client import LLMClient
from backend.services.reproducibility import (
    build_actual_prompt_hash,
    build_generation_envelope_hash,
    sha256_bytes,
    sha256_text,
)
from backend.services.structure_system_prompts import get_structure_system_prompt


redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
_ASSESSMENT_SCHEMA_VERSION = "1"
_MAX_ERROR_MESSAGE_LENGTH = 1000


def _publish_progress(experiment_id: int, run_id: int, condition_id: int, stage: str) -> None:
    redis_client.publish(
        f"experiment:{experiment_id}:progress",
        json.dumps({"run_id": run_id, "generation_id": run_id, "condition_id": condition_id, "stage": stage}),
    )


def _set_status(db: Session, run: Run, status: str) -> None:
    run.status = status
    db.commit()


def _factors_from_condition(condition) -> PromptFactors:
    return PromptFactors(
        concept_bridge=condition.concept_bridge_enabled,
        few_shot=condition.few_shot_enabled,
        reference_content=condition.reference_content_enabled,
        reasoning_guidance=condition.reasoning_guidance_enabled,
    )


def _structure_factor_inputs(condition, ordered_sources) -> dict[str, str]:
    source_hashes = {item.included_text_hash for item in ordered_sources}
    return {
        name: value
        for name, value in condition.factor_inputs.items()
        if sha256_text(value) not in source_hashes
    }


def _record_error(db: Session, run: Run, error_type: str, exc: Exception) -> None:
    db.rollback()
    run.status = "error"
    run.error_type = error_type
    run.error_message = str(exc)[:_MAX_ERROR_MESSAGE_LENGTH]
    run.completed_at = utc_now()
    db.commit()


def _retry_provider_failure(
    task, db: Session, run: Run, error_type: str, exc: Exception
) -> None:
    _record_error(db, run, error_type, exc)
    _publish_progress(run.experiment_id, run.id, run.condition_id, "error")
    raise task.retry(exc=exc, countdown=10)


@celery_app.task(bind=True, max_retries=3)
def run_generation_pipeline(self, run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run is None:
            return

        experiment = run.experiment
        condition = run.condition
        ordered_sources = sorted(run.source_documents, key=lambda item: (item.ordinal, item.id))
        _set_status(db, run, "prompting")
        _publish_progress(experiment.id, run.id, condition.id, "prompting")
        structure_system_prompt, structure_prompt_version = (
            get_structure_system_prompt(condition.prompt_structure)
        )
        structure_input = build_structure_input(
            course=experiment.course,
            topic=experiment.topic,
            learning_objectives=experiment.learning_objectives,
            assessment_type=experiment.assessment_type,
            difficulty=experiment.difficulty,
            number_of_questions=experiment.number_of_questions,
            factors=_factors_from_condition(condition),
            factor_inputs=_structure_factor_inputs(condition, ordered_sources),
        )
        llm = LLMClient(model=run.model)
        structure_started = time.perf_counter()
        try:
            structure_result = llm.generate(
                system_prompt=structure_system_prompt,
                user_message=structure_input,
                model_settings=run.model_settings,
            )
        except Exception as exc:
            _retry_provider_failure(
                self, db, run, "actual_prompt_provider_error", exc
            )

        structure_duration_ms = int(
            (time.perf_counter() - structure_started) * 1000
        )
        generation_context = build_generation_context(ordered_sources)
        source_hashes = [item.included_text_hash for item in ordered_sources]
        prompt = Prompt(
            run_id=run.id,
            prompt_structure=condition.prompt_structure,
            structure_system_prompt=structure_system_prompt,
            structure_input=structure_input,
            actual_prompt=structure_result.raw_text,
            actual_prompt_hash=build_actual_prompt_hash(
                structure_system_prompt=structure_system_prompt,
                structure_input=structure_input,
                actual_prompt=structure_result.raw_text,
                prompt_structure=condition.prompt_structure,
                structure_prompt_version=structure_prompt_version,
                actual_prompt_generator_version=ACTUAL_PROMPT_GENERATOR_VERSION,
                model_settings=run.model_settings,
            ),
            structure_prompt_version=structure_prompt_version,
            actual_prompt_generator_version=ACTUAL_PROMPT_GENERATOR_VERSION,
            structure_request_id=structure_result.provider_request_id,
            structure_model=structure_result.model_name,
            structure_model_version=structure_result.model_version,
            structure_finish_reason=structure_result.finish_reason,
            structure_duration_ms=structure_duration_ms,
            generation_context=generation_context,
            generation_envelope_hash=build_generation_envelope_hash(
                actual_prompt=structure_result.raw_text,
                generation_context=generation_context,
                model_settings=run.model_settings,
                source_hashes=source_hashes,
            ),
        )
        db.add(prompt)
        db.commit()
        db.refresh(prompt)

        try:
            validate_actual_prompt(condition.prompt_structure, prompt.actual_prompt)
        except ActualPromptValidationError as exc:
            _record_error(db, run, "actual_prompt_validation_error", exc)
            _publish_progress(experiment.id, run.id, condition.id, "error")
            return

        _set_status(db, run, "generating")
        _publish_progress(experiment.id, run.id, condition.id, "generating")
        generation_started = time.perf_counter()
        try:
            result = llm.generate(
                system_prompt=prompt.actual_prompt,
                user_message=prompt.generation_context,
                model_settings=run.model_settings,
            )
        except Exception as exc:
            _retry_provider_failure(self, db, run, "generation_provider_error", exc)

        assessment = Assessment(
            run_id=run.id,
            raw_response_text=result.raw_text,
            parsed_json=None,
            output_hash=sha256_text(result.raw_text),
            schema_version=_ASSESSMENT_SCHEMA_VERSION,
        )
        db.add(assessment)
        run.request_id = result.provider_request_id
        run.model = result.model_name
        run.version = result.model_version
        run.finish_reason = result.finish_reason
        run.duration_ms = int((time.perf_counter() - generation_started) * 1000)
        db.commit()
        db.refresh(assessment)

        try:
            generated = generate_questions(result.raw_text)
            assessment.parsed_json = generated.model_dump()
            run.generated_json = assessment.parsed_json
            db.commit()
        except (ValueError, ValidationError) as exc:
            _record_error(db, run, "assessment_parse_error", exc)
            _publish_progress(experiment.id, run.id, condition.id, "error")
            return

        try:
            _set_status(db, run, "documenting")
            _publish_progress(experiment.id, run.id, condition.id, "documenting")
            docx_bytes = build_assessment_docx(
                run_id=run.id,
                prompt_id=prompt.id,
                condition_code=condition.condition_code,
                run_number=run.run_number,
                course=experiment.course,
                topic=experiment.topic,
                questions=assessment.parsed_json["questions"],
            )
            db.add(DocumentArtifact(
                run_id=run.id,
                filename=f"blueprint-lab-run-{run.id}.docx",
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                content=docx_bytes,
                content_hash=sha256_bytes(docx_bytes),
            ))
            db.commit()
            run.status = "complete"
            run.completed_at = utc_now()
            db.commit()
            _publish_progress(experiment.id, run.id, condition.id, "complete")
        except Exception as exc:
            _record_error(db, run, "artifact_generation_error", exc)
            _publish_progress(experiment.id, run.id, condition.id, "error")
            raise self.retry(exc=exc, countdown=10)
    finally:
        db.close()
