import logging
import json
import time
import uuid
from typing import Optional

import redis
from celery.exceptions import Retry
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.celery_app import celery_app
from backend.config import settings
from backend.database import SessionLocal
from backend.models.experiment import utc_now
from backend.models.run import Assessment, Prompt, Run
from backend.schemas.experiment_schema import PromptFactors
from backend.schemas.assessment_schema import (
    ASSESSMENT_PROVIDER_SCHEMA,
    AssessmentGenerationResponse,
)
from backend.services.actual_prompt import (
    ACTUAL_PROMPT_GENERATOR_VERSION,
    OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION,
    OPENAI_TEMPLATE_PROVENANCE,
    ActualPromptValidationError,
    build_assessment_repair_system_prompt,
    build_assessment_repair_user_message,
    build_structure_input,
    build_generation_system_prompt,
    render_openai_actual_prompt,
    validate_actual_prompt,
)
from backend.services.assessment_evaluation import (
    EvaluationValidationError,
    persist_assessment_questions,
)
from backend.services.generation_context import build_generation_context
from backend.services.generator import generate_questions
from backend.services.document_artifact import save_assessment_artifact
from backend.services.llm_client import LLMClient, TruncatedResponseError
from backend.services.reference_pdfs import (
    ProviderFileAttachment,
    delete_provider_attachments,
)
from backend.services.reproducibility import (
    build_actual_prompt_hash,
    build_generation_envelope_hash,
    sha256_text,
)
from backend.services.structure_system_prompts import get_structure_system_prompt
from backend.services.usage_tracking import record_model_call
from backend.workers.evaluation_worker import run_llm_evaluation_pipeline


redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
logger = logging.getLogger(__name__)
_ASSESSMENT_SCHEMA_VERSION = "1"
_MAX_ERROR_MESSAGE_LENGTH = 1000
_MAX_ASSESSMENT_REPAIR_ATTEMPTS = 2


def _publish_progress(experiment_id: int, run_id: int, condition_id: int, stage: str) -> None:
    message = json.dumps(
        {
            "run_id": run_id,
            "generation_id": run_id,
            "condition_id": condition_id,
            "stage": stage,
        }
    )
    redis_client.publish(f"experiment:{experiment_id}:progress", message)
    redis_client.publish(f"run:{run_id}:progress", message)


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
    run.progress_message = "Assessment generation failed"
    run.error_type = error_type
    run.error_message = str(exc)[:_MAX_ERROR_MESSAGE_LENGTH]
    run.completed_at = utc_now()
    db.commit()


def _retry_provider_failure(
    task, db: Session, run: Run, error_type: str, exc: Exception
) -> None:
    _record_error(db, run, error_type, exc)
    _publish_progress(
        run.experiment_id, run.id, run.condition_id, "error"
    )
    raise task.retry(exc=exc, countdown=10)


def _call_gemini(
    task,
    db: Session,
    run: Run,
    llm: LLMClient,
    *,
    stage: str,
    system_prompt: str,
    user_message: str,
    model_settings: dict,
    response_schema=None,
    attachments=None,
):
    call_id = str(uuid.uuid4())
    attempt = sum(1 for item in run.model_call_usages if item.stage == stage) + 1
    request = {
        "system_prompt": system_prompt,
        "user_message": user_message,
        "model_settings": model_settings,
    }
    if response_schema is not None:
        request["response_schema"] = response_schema
    if attachments:
        request["attachments"] = attachments
    try:
        result = llm.generate(**request)
    except TruncatedResponseError as exc:
        record_model_call(
            db,
            run=run,
            call_id=call_id,
            stage=stage,
            attempt=attempt,
            result=exc.result,
        )
        raise
    except Exception:
        record_model_call(
            db,
            run=run,
            call_id=call_id,
            stage=stage,
            attempt=attempt,
            failed=True,
        )
        raise
    record_model_call(
        db,
        run=run,
        call_id=call_id,
        stage=stage,
        attempt=attempt,
        result=result,
    )
    return result


def _cleanup_provider_files(
    llm: Optional[LLMClient],
    attachments: list[ProviderFileAttachment],
) -> None:
    if not attachments:
        return
    if llm is None:
        try:
            llm = LLMClient()
        except Exception as exc:
            logger.warning(
                "Reference PDF provider cleanup client initialization failed",
                extra={"error_type": type(exc).__name__},
            )
            return
    delete_provider_attachments(llm, list(reversed(attachments)))


def _is_reference_pdf_unavailable(exc: Exception) -> bool:
    message = str(exc).casefold()
    mentions_file = "file" in message or "attachment" in message
    unavailable = any(
        phrase in message for phrase in ("not found", "unavailable", "expired")
    )
    return mentions_file and unavailable


@celery_app.task(bind=True, max_retries=3)
def run_generation_pipeline(
    self,
    run_id: int,
    attachment_metadata: Optional[list[dict[str, str]]] = None,
) -> None:
    attachments = [
        ProviderFileAttachment.from_dict(item)
        for item in (attachment_metadata or [])
    ]
    db = SessionLocal()
    llm = None
    preserve_provider_files = False
    try:
        run = db.get(Run, run_id)
        if run is None:
            return
        if (
            run.status == "complete"
            and run.assessment is not None
            and run.assessment.parsed_json is not None
            and run.document_artifact is not None
        ):
            run_llm_evaluation_pipeline.delay(run.id)
            return

        experiment = run.experiment
        condition = run.condition
        run.error_type = None
        run.error_message = None
        run.completed_at = None
        if run.started_at is None:
            run.started_at = utc_now()
        ordered_sources = sorted(run.source_documents, key=lambda item: (item.ordinal, item.id))
        llm = LLMClient(model=run.model)
        prompt = run.prompt
        if prompt is None:
            run.progress_message = "Preparing Prompt"
            _set_status(db, run, "prompting")
            _publish_progress(
                experiment.id, run.id, condition.id, "prompting"
            )
            factors = _factors_from_condition(condition)
            structure_input = build_structure_input(
                course=experiment.course,
                topic=experiment.topic,
                learning_objectives=experiment.learning_objectives,
                assessment_type=experiment.assessment_type,
                difficulty=experiment.difficulty,
                number_of_questions=experiment.number_of_questions,
                estimated_time_minutes=experiment.estimated_time_minutes,
                cognitive_demand=experiment.cognitive_demand,
                additional_instruction=experiment.additional_instruction,
                factors=factors,
                factor_inputs=_structure_factor_inputs(condition, ordered_sources),
                reference_pdf_filenames=run.reference_pdf_filenames,
            )
            structure_started = time.perf_counter()
            if condition.prompt_structure == "openai":
                try:
                    actual_prompt = render_openai_actual_prompt(
                        course=experiment.course,
                        topic=experiment.topic,
                        learning_objectives=experiment.learning_objectives,
                        assessment_type=experiment.assessment_type,
                        difficulty=experiment.difficulty,
                        number_of_questions=experiment.number_of_questions,
                        estimated_time_minutes=experiment.estimated_time_minutes,
                        cognitive_demand=experiment.cognitive_demand,
                        additional_instruction=experiment.additional_instruction,
                        factors=factors,
                        factor_inputs=condition.factor_inputs,
                        reference_pdf_filenames=run.reference_pdf_filenames,
                    )
                except ActualPromptValidationError as exc:
                    _record_error(
                        db, run, "actual_prompt_validation_error", exc
                    )
                    _publish_progress(
                        experiment.id,
                        run.id,
                        condition.id,
                        "error",
                    )
                    return
                structure_system_prompt = OPENAI_TEMPLATE_PROVENANCE
                structure_prompt_version = OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION
                structure_request_id = None
                structure_model = "local-template-renderer"
                structure_model_version = OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION
                structure_finish_reason = "LOCAL"
            else:
                structure_system_prompt, structure_prompt_version = (
                    get_structure_system_prompt(condition.prompt_structure)
                )
                try:
                    structure_result = _call_gemini(
                        self,
                        db,
                        run,
                        llm,
                        stage="actual_prompt",
                        system_prompt=structure_system_prompt,
                        user_message=structure_input,
                        model_settings=run.model_settings,
                    )
                except Exception as exc:
                    _retry_provider_failure(
                        self, db, run, "actual_prompt_provider_error", exc
                    )
                actual_prompt = structure_result.raw_text
                structure_request_id = structure_result.provider_request_id
                structure_model = structure_result.model_name
                structure_model_version = structure_result.model_version
                structure_finish_reason = structure_result.finish_reason

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
                actual_prompt=actual_prompt,
                actual_prompt_hash=build_actual_prompt_hash(
                    structure_system_prompt=structure_system_prompt,
                    structure_input=structure_input,
                    actual_prompt=actual_prompt,
                    prompt_structure=condition.prompt_structure,
                    structure_prompt_version=structure_prompt_version,
                    actual_prompt_generator_version=ACTUAL_PROMPT_GENERATOR_VERSION,
                    model_settings=run.model_settings,
                ),
                structure_prompt_version=structure_prompt_version,
                actual_prompt_generator_version=ACTUAL_PROMPT_GENERATOR_VERSION,
                structure_request_id=structure_request_id,
                structure_model=structure_model,
                structure_model_version=structure_model_version,
                structure_finish_reason=structure_finish_reason,
                structure_duration_ms=structure_duration_ms,
                generation_context=generation_context,
                generation_envelope_hash=build_generation_envelope_hash(
                    actual_prompt=actual_prompt,
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
            _publish_progress(
                experiment.id, run.id, condition.id, "error"
            )
            return

        if run.assessment is not None and run.assessment.parsed_json is not None:
            try:
                persist_assessment_questions(db, run.assessment)
                run.status = "documenting"
                run.progress_message = "Creating assessment document"
                db.commit()
                _publish_progress(
                    experiment.id, run.id, condition.id, "documenting"
                )
                save_assessment_artifact(db, run)
                run.viewer_ready_at = run.viewer_ready_at or utc_now()
                run.status = "complete"
                run.progress_message = "Complete"
                run.completed_at = utc_now()
                db.commit()
                _publish_progress(
                    experiment.id, run.id, condition.id, "complete"
                )
            except Exception as exc:
                _record_error(db, run, "document_generation_error", exc)
                _publish_progress(experiment.id, run.id, condition.id, "error")
                return
            run_llm_evaluation_pipeline.delay(run.id)
            return

        run.progress_message = "Generating Assessment"
        _set_status(db, run, "generating")
        _publish_progress(
            experiment.id, run.id, condition.id, "generating"
        )
        generation_started = time.perf_counter()
        try:
            result = _call_gemini(
                self,
                db,
                run,
                llm,
                stage="assessment",
                system_prompt=build_generation_system_prompt(prompt.actual_prompt),
                user_message=prompt.generation_context,
                model_settings=run.model_settings,
                response_schema=ASSESSMENT_PROVIDER_SCHEMA,
                attachments=attachments,
            )
        except Exception as exc:
            if attachments and _is_reference_pdf_unavailable(exc):
                sanitized = RuntimeError(
                    "An attached reference PDF is unavailable. Upload fresh PDFs and retry."
                )
                _record_error(db, run, "reference_pdf_unavailable", sanitized)
                _publish_progress(
                    experiment.id, run.id, condition.id, "error"
                )
                return
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
            run.progress_message = "Validating Assessment"
            _set_status(db, run, "generating")
            _publish_progress(
                experiment.id, run.id, condition.id, "generating"
            )
            generated = None
            for repair_attempt in range(_MAX_ASSESSMENT_REPAIR_ATTEMPTS + 1):
                try:
                    generated = generate_questions(result.raw_text)
                    break
                except ValidationError as exc:
                    if repair_attempt == _MAX_ASSESSMENT_REPAIR_ATTEMPTS:
                        raise
                    validation_error = str(exc)

                run.progress_message = "Repairing Assessment"
                db.commit()
                _publish_progress(
                    experiment.id, run.id, condition.id, "generating"
                )
                try:
                    result = _call_gemini(
                        self,
                        db,
                        run,
                        llm,
                        stage="repair",
                        system_prompt=build_assessment_repair_system_prompt(
                            prompt.actual_prompt
                        ),
                        user_message=build_assessment_repair_user_message(
                            result.raw_text,
                            validation_error,
                        ),
                        model_settings=run.model_settings,
                        response_schema=ASSESSMENT_PROVIDER_SCHEMA,
                        attachments=attachments,
                    )
                except Exception as exc:
                    if attachments and _is_reference_pdf_unavailable(exc):
                        exc = RuntimeError(
                            "An attached reference PDF is unavailable. Upload fresh PDFs and retry."
                        )
                        error_type = "reference_pdf_unavailable"
                    else:
                        error_type = "assessment_repair_provider_error"
                    _record_error(
                        db,
                        run,
                        error_type,
                        exc,
                    )
                    _publish_progress(
                        experiment.id, run.id, condition.id, "error"
                    )
                    return

                assessment.raw_response_text = result.raw_text
                assessment.output_hash = sha256_text(result.raw_text)
                run.request_id = result.provider_request_id
                run.model = result.model_name
                run.version = result.model_version
                run.finish_reason = result.finish_reason
                run.duration_ms = int(
                    (time.perf_counter() - generation_started) * 1000
                )
                db.commit()
            assert generated is not None
            assessment.parsed_json = generated.model_dump()
            run.generated_json = assessment.parsed_json
            persist_assessment_questions(db, assessment)
            run.status = "documenting"
            run.progress_message = "Creating assessment document"
            db.commit()
            _publish_progress(
                experiment.id, run.id, condition.id, "documenting"
            )
            save_assessment_artifact(db, run)
            run.viewer_ready_at = utc_now()
            run.status = "complete"
            run.progress_message = "Complete"
            run.completed_at = utc_now()
            db.commit()
        except (ValueError, ValidationError, EvaluationValidationError) as exc:
            error_type = (
                "document_generation_error"
                if run.status == "documenting"
                else "assessment_parse_error"
            )
            _record_error(db, run, error_type, exc)
            _publish_progress(
                experiment.id, run.id, condition.id, "error"
            )
            return
        except Exception as exc:
            _record_error(db, run, "document_generation_error", exc)
            _publish_progress(experiment.id, run.id, condition.id, "error")
            return
        _publish_progress(
            experiment.id, run.id, condition.id, "complete"
        )
        run_llm_evaluation_pipeline.delay(run.id)
    except Retry:
        preserve_provider_files = True
        raise
    finally:
        db.close()
        if not preserve_provider_files:
            _cleanup_provider_files(llm, attachments)
