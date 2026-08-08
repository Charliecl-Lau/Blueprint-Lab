import logging
import json
import time
import uuid
from typing import Optional

import redis
from celery.exceptions import MaxRetriesExceededError, Retry
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.celery_app import celery_app
from backend.config import settings
from backend.database import SessionLocal
from backend.models.experiment import utc_now
from backend.models import AssessmentRepairAttempt, ModelCallUsage
from backend.models.run import Assessment, Prompt, Run
from backend.schemas.experiment_schema import PromptFactors
from backend.schemas.assessment_schema import (
    ASSESSMENT_PROVIDER_SCHEMA,
    ASSESSMENT_QUESTION_PROVIDER_SCHEMA,
    ASSESSMENT_SEGMENT_REPLACEMENT_SCHEMA,
    ASSESSMENT_CANONICAL_QUESTION_SCHEMA,
    AssessmentGenerationResponse,
    ProviderSegmentReplacement,
    QuestionResponse,
)
from backend.services.actual_prompt import (
    ACTUAL_PROMPT_GENERATOR_VERSION,
    OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION,
    OPENAI_TEMPLATE_PROVENANCE,
    ActualPromptValidationError,
    build_assessment_repair_system_prompt,
    build_question_repair_user_message,
    build_segment_repair_user_message,
    build_structure_input,
    build_generation_system_prompt,
    render_openai_actual_prompt,
    validate_actual_prompt,
)
from backend.services.assessment_evaluation import (
    EvaluationValidationError,
    persist_assessment_questions,
)
from backend.services.assessment_recovery_service import (
    mark_strictly_valid,
    recover_saved_assessment,
    set_warning_run_state,
)
from backend.services.assessment_traceability import enrich_assessment_traceability
from backend.services.generation_context import build_generation_context
from backend.services.generator import (
    generate_questions,
    parse_segmented_question,
)
from backend.services.assessment_segment_compiler import (
    AssessmentCompilationError,
    audit_provider_question,
    compile_provider_assessment,
    compile_provider_question,
)
from backend.services.assessment_local_repair import (
    LocalizedRepairRejected,
    apply_segment_replacement,
    content_hash,
    extract_segment_replacement_from_question,
    segment_target,
)
from backend.services.document_artifact import save_assessment_artifact
from backend.services.document_generators import document_generator_registry
from backend.services.docx_authoring_pipeline import DocxAuthoringPipeline
from backend.services.docx_sandbox_client import SandboxTransportError
from backend.services.llm_client import (
    LLMClient,
    TruncatedResponseError,
    _parse_json,
    is_retryable_provider_error,
)
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
_ASSESSMENT_SCHEMA_VERSION = "2"
_MAX_ERROR_MESSAGE_LENGTH = 1000
_MAX_ASSESSMENT_REPAIR_ATTEMPTS = settings.assessment_max_repair_attempts


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
    retries = getattr(task.request, "retries", 0)
    max_retries = getattr(task, "max_retries", None)
    if max_retries is not None and retries >= max_retries:
        _record_error(db, run, error_type, exc)
        _publish_progress(
            run.experiment_id, run.id, run.condition_id, "error"
        )
        raise exc

    db.rollback()
    run.status = "pending"
    run.progress_message = "Provider connection failed; retrying generation"
    run.error_type = error_type
    run.error_message = str(exc)[:_MAX_ERROR_MESSAGE_LENGTH]
    run.completed_at = None
    db.commit()
    _publish_progress(
        run.experiment_id, run.id, run.condition_id, "retrying"
    )
    try:
        raise task.retry(exc=exc, countdown=10)
    except MaxRetriesExceededError:
        _record_error(db, run, error_type, exc)
        _publish_progress(
            run.experiment_id, run.id, run.condition_id, "error"
        )
        raise


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
    requested_at = utc_now()
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
            requested_at=requested_at,
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
            requested_at=requested_at,
        )
        raise
    record_model_call(
        db,
        run=run,
        call_id=call_id,
        stage=stage,
        attempt=attempt,
        result=result,
        requested_at=requested_at,
    )
    return result


def _question_issues(error: ValidationError, ordinal: int) -> list[dict]:
    return [
        {
            "code": str(item.get("type", "validation_error")),
            "question_ordinal": ordinal,
            "field_path": ".".join(str(value) for value in item.get("loc", ())),
            "message": str(item.get("msg", "Question validation failed")),
            "excerpt": None,
            "repair_scope": "question",
        }
        for item in error.errors()
    ]


def _repair_segmented_questions(
    task,
    db: Session,
    run: Run,
    llm: LLMClient,
    error: AssessmentCompilationError,
    *,
    actual_prompt: str,
    model_settings: dict,
    attachments,
):
    provider = error.provider.model_copy(deep=True)
    last_result = None
    issues = list(error.issues)
    for repair_attempt in range(1, _MAX_ASSESSMENT_REPAIR_ATTEMPTS + 1):
        if not issues:
            break
        selected = issues[0]
        issue = selected.as_dict()
        if selected.question_ordinal is None:
            raise EvaluationValidationError(json.dumps([issue], ensure_ascii=False))
        ordinal = selected.question_ordinal
        target = segment_target(provider, selected.field_path)
        if target is not None:
            before_content = target.content
            repair_scope = "content_block"
            target_path = target.path
            response_schema = ASSESSMENT_SEGMENT_REPLACEMENT_SCHEMA
            user_message = build_segment_repair_user_message(
                target_path=target_path,
                segment_payload=before_content,
                issue=issue,
            )
        else:
            before_content = provider.questions[ordinal].model_dump(mode="json")
            repair_scope = "question"
            target_path = f"questions.{ordinal}"
            response_schema = ASSESSMENT_QUESTION_PROVIDER_SCHEMA
            user_message = build_question_repair_user_message(
                ordinal, before_content, [item.as_dict() for item in issues if item.question_ordinal == ordinal]
            )

        evidence = AssessmentRepairAttempt(
            run_id=run.id,
            assessment_id=run.assessment.id if run.assessment is not None else None,
            question_ordinal=ordinal,
            attempt_number=repair_attempt,
            issues=[issue],
            status="pending",
            repair_type="structural",
            error_type=issue.get("error_type"),
            validator_code=issue.get("code"),
            validator_message=issue.get("message"),
            target_path=target_path,
            target_section=issue.get("target_section"),
            question_id=issue.get("question_id"),
            solution_id=issue.get("solution_id"),
            equation_id=issue.get("equation_id"),
            repair_scope=repair_scope,
            before_content=before_content,
            before_hash=content_hash(before_content),
            prompt_version=run.prompt.structure_prompt_version if run.prompt else None,
        )
        db.add(evidence)
        db.commit()  # Append-only intent exists before the external call starts.
        run.progress_message = f"Repairing {target_path}"
        db.commit()
        _publish_progress(run.experiment_id, run.id, run.condition_id, "generating")
        try:
            last_result = _call_gemini(
                task,
                db,
                run,
                llm,
                stage="repair",
                system_prompt=build_assessment_repair_system_prompt(actual_prompt),
                user_message=user_message,
                model_settings=model_settings,
                response_schema=response_schema,
                attachments=attachments,
            )
        except Exception as exc:
            usage = (
                db.query(ModelCallUsage)
                .filter_by(run_id=run.id, stage="repair")
                .order_by(ModelCallUsage.id.desc())
                .first()
            )
            if usage is not None:
                evidence.model_call_usage_id = usage.id
                evidence.model_call_id = usage.call_id
            evidence.status = "invalid"
            evidence.success = False
            evidence.failure_reason = str(exc)[:_MAX_ERROR_MESSAGE_LENGTH]
            evidence.completed_at = utc_now()
            db.commit()
            raise
        evidence.status = "response"
        evidence.model = last_result.model_name
        usage = (
            db.query(ModelCallUsage)
            .filter_by(run_id=run.id, stage="repair")
            .order_by(ModelCallUsage.id.desc())
            .first()
        )
        if usage is not None:
            evidence.model_call_usage_id = usage.id
            evidence.model_call_id = usage.call_id
            evidence.token_usage = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
            }
        try:
            if target is not None:
                try:
                    replacement = ProviderSegmentReplacement.model_validate_json(
                        last_result.raw_text
                    )
                except ValidationError:
                    # Read old in-flight provider responses safely: extract only the
                    # target fragment and reject any unrelated question mutation.
                    candidate = parse_segmented_question(last_result.raw_text)
                    replacement = extract_segment_replacement_from_question(
                        provider, target, candidate
                    )
                evidence.after_content = replacement.model_dump(mode="json")
                evidence.after_hash = content_hash(evidence.after_content)
                patched = apply_segment_replacement(provider, target, replacement)
            else:
                repaired = parse_segmented_question(last_result.raw_text)
                evidence.after_content = repaired.model_dump(mode="json")
                evidence.after_hash = content_hash(evidence.after_content)
                patched = provider.model_copy(deep=True)
                patched.questions[ordinal] = repaired
            compile_provider_assessment(patched)
        except (ValidationError, ValueError, LocalizedRepairRejected, AssessmentCompilationError) as exc:
            evidence.status = "invalid"
            evidence.success = False
            evidence.failure_reason = str(exc)[:_MAX_ERROR_MESSAGE_LENGTH]
            evidence.completed_at = utc_now()
            db.commit()
            if isinstance(exc, AssessmentCompilationError):
                issues = list(exc.issues)
            elif target is None and isinstance(exc, ValidationError):
                issues = []
            if repair_attempt == _MAX_ASSESSMENT_REPAIR_ATTEMPTS:
                raise EvaluationValidationError(evidence.failure_reason) from exc
            continue
        provider = patched
        try:
            generated = compile_provider_assessment(provider)
            issues = []
        except AssessmentCompilationError as exc:
            issues = list(exc.issues)
            generated = None
        if generated is not None or all(
            item.field_path != selected.field_path for item in issues
        ):
            evidence.status = "merged"
            evidence.success = True
        else:
            evidence.status = "invalid"
            evidence.success = False
            evidence.failure_reason = "target validation error remains after patch"
        evidence.completed_at = utc_now()
        db.commit()
        if not evidence.success and repair_attempt == _MAX_ASSESSMENT_REPAIR_ATTEMPTS:
            raise EvaluationValidationError(evidence.failure_reason)

    try:
        generated = compile_provider_assessment(provider)
    except AssessmentCompilationError as exc:
        raise EvaluationValidationError(str(exc)) from exc
    return generated, provider.model_dump_json(), last_result


def _repair_legacy_question(
    task,
    db: Session,
    run: Run,
    llm: LLMClient,
    raw_text: str,
    validation_error: ValidationError,
    *,
    actual_prompt: str,
    model_settings: dict,
    attachments,
):
    payload = _parse_json(raw_text)
    questions = payload.get("questions") if isinstance(payload, dict) else None
    error_items = validation_error.errors()
    location = error_items[0].get("loc", ()) if error_items else ()
    if (
        not isinstance(questions, list)
        or len(location) < 2
        or location[0] != "questions"
        or not isinstance(location[1], int)
        or location[1] >= len(questions)
    ):
        raise EvaluationValidationError(
            f"structural repair target could not be localized: {validation_error}"
        )
    ordinal = location[1]
    current = json.loads(json.dumps(payload))
    last_result = None
    for attempt_number in range(1, _MAX_ASSESSMENT_REPAIR_ATTEMPTS + 1):
        issues = _question_issues(validation_error, ordinal)
        for issue in issues:
            issue["target_path"] = f"questions.{ordinal}"
            issue["target_section"] = "question"
            issue["error_type"] = "structural_validation_error"
            issue["expected_structure"] = "QuestionResponse"
            issue["observed_structure"] = current["questions"][ordinal]
        before = current["questions"][ordinal]
        evidence = AssessmentRepairAttempt(
            run_id=run.id,
            assessment_id=run.assessment.id if run.assessment else None,
            question_ordinal=ordinal,
            attempt_number=attempt_number,
            issues=issues,
            status="pending",
            repair_type="structural",
            error_type="structural_validation_error",
            validator_code=issues[0]["code"],
            validator_message=issues[0]["message"],
            target_path=f"questions.{ordinal}",
            target_section="question",
            repair_scope="question",
            before_content=before,
            before_hash=content_hash(before),
            prompt_version=run.prompt.structure_prompt_version if run.prompt else None,
        )
        db.add(evidence)
        db.commit()
        try:
            last_result = _call_gemini(
                task,
                db,
                run,
                llm,
                stage="repair",
                system_prompt=build_assessment_repair_system_prompt(actual_prompt),
                user_message=build_question_repair_user_message(ordinal, before, issues),
                model_settings=model_settings,
                response_schema=ASSESSMENT_CANONICAL_QUESTION_SCHEMA,
                attachments=attachments,
            )
            usage = (
                db.query(ModelCallUsage)
                .filter_by(run_id=run.id, stage="repair")
                .order_by(ModelCallUsage.id.desc())
                .first()
            )
            if usage is not None:
                evidence.model_call_usage_id = usage.id
                evidence.model_call_id = usage.call_id
                evidence.model = last_result.model_name
                evidence.token_usage = {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                }
            response_payload = _parse_json(last_result.raw_text)
            if isinstance(response_payload, dict) and "questions" in response_payload:
                response_payload = response_payload["questions"][ordinal]
            repaired = QuestionResponse.model_validate(response_payload)
            evidence.after_content = response_payload
            evidence.after_hash = content_hash(evidence.after_content)
            candidate = json.loads(json.dumps(current))
            candidate["questions"][ordinal] = response_payload
            generated = generate_questions(json.dumps(candidate))
        except Exception as exc:
            usage = (
                db.query(ModelCallUsage)
                .filter_by(run_id=run.id, stage="repair")
                .order_by(ModelCallUsage.id.desc())
                .first()
            )
            if usage is not None and evidence.model_call_usage_id is None:
                evidence.model_call_usage_id = usage.id
                evidence.model_call_id = usage.call_id
            evidence.status = "invalid"
            evidence.success = False
            evidence.failure_reason = str(exc)[:_MAX_ERROR_MESSAGE_LENGTH]
            evidence.completed_at = utc_now()
            db.commit()
            if isinstance(exc, ValidationError):
                validation_error = exc
            if attempt_number == _MAX_ASSESSMENT_REPAIR_ATTEMPTS:
                raise EvaluationValidationError(str(exc)) from exc
            continue
        current = candidate
        evidence.status = "merged"
        evidence.success = True
        evidence.completed_at = utc_now()
        db.commit()
        return generated, json.dumps(current), last_result
    raise EvaluationValidationError("localized question repair limit exhausted")


def _cleanup_provider_files(
    llm: Optional[LLMClient],
    attachments: list[ProviderFileAttachment],
) -> None:
    if not attachments:
        return
    if llm is None:
        try:
            llm = LLMClient(provider=attachments[0].provider)
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


def _dispatch_evaluation(run_id: int) -> None:
    try:
        run_llm_evaluation_pipeline.delay(run_id)
    except Exception as exc:
        logger.warning(
            "Completed assessment evaluation dispatch failed",
            extra={"run_id": run_id, "error_type": type(exc).__name__},
        )


def _create_document(
    db: Session,
    run: Run,
    attachments: list[ProviderFileAttachment],
) -> bool:
    """Create the configured artifact and return whether version 2 is canonical."""
    messages = {
        "documenting": "Creating assessment document",
        "docx_authoring": "Sol is generating the Word document" if settings.docx_generation_backend == "luna_direct" else ("Gemini is designing the Word document" if settings.docx_generation_backend == "agentic_tools" else "Authoring assessment document"),
        "docx_executing": "Applying document operations" if settings.docx_generation_backend == "agentic_tools" else "Executing DOCX program",
        "docx_validating": "Structurally verifying the Luna Word document" if settings.docx_generation_backend == "luna_direct" else ("Rendering and verifying the Word document" if settings.docx_generation_backend == "agentic_tools" else "Validating assessment document"),
        "docx_repairing": "Gemini is revising the rendered document" if settings.docx_generation_backend == "agentic_tools" else "Repairing assessment document",
    }

    def progress(stage: str) -> None:
        run.status = stage
        run.progress_message = messages[stage]
        db.commit()
        _publish_progress(run.experiment_id, run.id, run.condition_id, stage)

    generator = document_generator_registry.get(settings.docx_generation_backend)
    result = generator.generate(db=db, run=run, attachments=attachments, progress=progress)
    if result.succeeded:
        return True
    run.status = "rewrite_failed"
    run.progress_message = "Assessment rewrite failed; original remains available"
    run.error_type = "docx_rewrite_failed"
    run.error_message = ", ".join(result.safe_issue_codes)[:1000]
    run.viewer_ready_at = run.viewer_ready_at or utc_now()
    run.completed_at = utc_now()
    db.commit()
    _publish_progress(run.experiment_id, run.id, run.condition_id, "rewrite_failed")
    return False


@celery_app.task(bind=True, max_retries=3)
def run_docx_rewrite_pipeline(
    self,
    run_id: int,
    idempotency_key: str,
) -> None:
    """Execute only a newly reserved DOCX cycle for an existing failed run."""
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run is None:
            return
        reserved = next(
            (
                item
                for item in run.docx_authoring_attempts
                if item.idempotency_key == idempotency_key
            ),
            None,
        )
        if reserved is None:
            return
        if run.status == "complete" and run.canonical_assessment is not None:
            return

        agentic = settings.docx_generation_backend == "agentic_tools"
        luna_direct = settings.docx_generation_backend == "luna_direct"
        messages = {
            "documenting": "Creating assessment document",
            "docx_authoring": "Luna is generating the Word document" if luna_direct else ("Gemini is designing the Word document" if agentic else "Authoring Word document"),
            "docx_executing": "Applying document operations" if agentic else "Building Word document in sandbox",
            "docx_validating": "Structurally verifying the Luna Word document" if luna_direct else ("Rendering and verifying the Word document" if agentic else "Verifying Word document"),
            "docx_repairing": "Gemini is revising the rendered document" if agentic else "Repairing Word document",
        }

        def progress(stage: str) -> None:
            run.status = stage
            run.progress_message = messages[stage]
            db.commit()
            _publish_progress(run.experiment_id, run.id, run.condition_id, stage)

        generator = document_generator_registry.get(settings.docx_generation_backend)
        result = generator.generate(db=db, run=run, attachments=(), progress=progress)
        if result.succeeded:
            run.status = "complete"
            run.progress_message = "Complete"
            run.viewer_ready_at = utc_now()
            run.completed_at = utc_now()
            run.error_type = None
            run.error_message = None
            db.commit()
            _publish_progress(run.experiment_id, run.id, run.condition_id, "complete")
            _dispatch_evaluation(run.id)
            return

        run.status = "rewrite_failed"
        run.progress_message = "Word rewrite failed; original remains available"
        run.error_type = "docx_rewrite_failed"
        run.error_message = ", ".join(result.safe_issue_codes)[:1000]
        run.viewer_ready_at = run.viewer_ready_at or utc_now()
        run.completed_at = utc_now()
        db.commit()
        _publish_progress(run.experiment_id, run.id, run.condition_id, "rewrite_failed")
    except SandboxTransportError as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    finally:
        db.close()


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
            _dispatch_evaluation(run.id)
            return

        experiment = run.experiment
        condition = run.condition
        run.error_type = None
        run.error_message = None
        run.completed_at = None
        if run.started_at is None:
            run.started_at = utc_now()
        ordered_sources = sorted(run.source_documents, key=lambda item: (item.ordinal, item.id))
        llm = LLMClient(provider=run.provider, model=run.model)
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
            execution_system_prompt = build_generation_system_prompt(actual_prompt)
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
                execution_system_prompt=execution_system_prompt,
                execution_user_message=generation_context,
                execution_schema_version=_ASSESSMENT_SCHEMA_VERSION,
                generation_envelope_hash=build_generation_envelope_hash(
                    execution_system_prompt=execution_system_prompt,
                    execution_user_message=generation_context,
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

        if (
            run.assessment is not None
            and run.assessment.parsed_json is not None
            and run.assessment.validation_status == "valid"
        ):
            try:
                persist_assessment_questions(db, run.assessment)
                enrich_assessment_traceability(db, run.assessment)
                if not _create_document(db, run, attachments):
                    return
                run.viewer_ready_at = run.viewer_ready_at or utc_now()
                run.status = "complete"
                run.progress_message = "Complete"
                run.completed_at = utc_now()
                db.commit()
                _publish_progress(
                    experiment.id, run.id, condition.id, "complete"
                )
            except SandboxTransportError as exc:
                _retry_provider_failure(
                    self, db, run, "docx_sandbox_transport_error", exc
                )
            except Exception as exc:
                if is_retryable_provider_error(exc):
                    _retry_provider_failure(
                        self, db, run, "document_generation_provider_error", exc
                    )
                _record_error(db, run, "document_generation_error", exc)
                _publish_progress(experiment.id, run.id, condition.id, "error")
                return
            _dispatch_evaluation(run.id)
            return
        if (
            run.assessment is not None
            and run.assessment.validation_status == "warning"
            and run.assessment.defects_accepted_at is None
        ):
            _publish_progress(
                experiment.id, run.id, condition.id, "complete_with_warnings"
            )
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
                system_prompt=prompt.execution_system_prompt,
                user_message=prompt.execution_user_message,
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
            version=1,
            kind="original_generation",
            raw_response_text=result.raw_text,
            parsed_json=None,
            output_hash=sha256_text(result.raw_text),
            schema_version=_ASSESSMENT_SCHEMA_VERSION,
            validation_status="invalid",
        )
        run.assessment = assessment
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
            accepted_assessment = assessment
            try:
                generated = generate_questions(
                    result.raw_text,
                    expected_questions=experiment.number_of_questions,
                )
            except AssessmentCompilationError as exc:
                generated, compiled_raw, last_repair_result = _repair_segmented_questions(
                    self,
                    db,
                    run,
                    llm,
                    exc,
                    actual_prompt=prompt.actual_prompt,
                    model_settings=run.model_settings,
                    attachments=attachments,
                )
                accepted_assessment = Assessment(
                    run_id=run.id,
                    version=2,
                    kind="localized_repair",
                    source_assessment_id=assessment.id,
                    raw_response_text=compiled_raw,
                    parsed_json=None,
                    output_hash=sha256_text(compiled_raw),
                    schema_version=_ASSESSMENT_SCHEMA_VERSION,
                    validation_status="invalid",
                )
                run.assessment = accepted_assessment
                if last_repair_result is not None:
                    run.request_id = last_repair_result.provider_request_id
                    run.model = last_repair_result.model_name
                    run.version = last_repair_result.model_version
                    run.finish_reason = last_repair_result.finish_reason
                run.duration_ms = int((time.perf_counter() - generation_started) * 1000)
                db.commit()
            except ValidationError as exc:
                generated, compiled_raw, last_repair_result = _repair_legacy_question(
                    self,
                    db,
                    run,
                    llm,
                    result.raw_text,
                    exc,
                    actual_prompt=prompt.actual_prompt,
                    model_settings=run.model_settings,
                    attachments=attachments,
                )
                accepted_assessment = Assessment(
                    run_id=run.id,
                    version=2,
                    kind="localized_repair",
                    source_assessment_id=assessment.id,
                    raw_response_text=compiled_raw,
                    parsed_json=None,
                    output_hash=sha256_text(compiled_raw),
                    schema_version=_ASSESSMENT_SCHEMA_VERSION,
                    validation_status="invalid",
                )
                run.assessment = accepted_assessment
                db.commit()
            except ValueError as exc:
                # Unlocatable document-level failures are retained for research but
                # never sent through a full-response regeneration fallback.
                raise EvaluationValidationError(
                    f"structural repair target could not be localized: {exc}"
                ) from exc

            mark_strictly_valid(accepted_assessment, generated.model_dump())
            persist_assessment_questions(db, accepted_assessment)
            enrich_assessment_traceability(db, accepted_assessment)
            if not _create_document(db, run, attachments):
                return
            run.viewer_ready_at = utc_now()
            run.status = "complete"
            run.progress_message = "Complete"
            run.completed_at = utc_now()
            db.commit()
        except SandboxTransportError as exc:
            _retry_provider_failure(
                self, db, run, "docx_sandbox_transport_error", exc
            )
        except (ValueError, ValidationError, EvaluationValidationError) as exc:
            if run.status in {
                    "documenting",
                    "docx_authoring",
                    "docx_executing",
                    "docx_validating",
                    "docx_repairing",
                }:
                error_type = "document_generation_error"
            elif run.assessment_repair_attempts:
                error_type = "structural_repair_failed"
            else:
                try:
                    json.loads(run.assessment.raw_response_text)
                except (TypeError, json.JSONDecodeError):
                    error_type = "assessment_parse_error"
                else:
                    error_type = "structural_repair_failed"
            _record_error(db, run, error_type, exc)
            _publish_progress(
                experiment.id, run.id, condition.id, "error"
            )
            return
        except Exception as exc:
            if is_retryable_provider_error(exc):
                _retry_provider_failure(
                    self, db, run, "document_generation_provider_error", exc
                )
            _record_error(db, run, "document_generation_error", exc)
            _publish_progress(experiment.id, run.id, condition.id, "error")
            return
        _publish_progress(
            experiment.id, run.id, condition.id, "complete"
        )
        _dispatch_evaluation(run.id)
    except Retry:
        preserve_provider_files = True
        raise
    finally:
        db.close()
        if not preserve_provider_files:
            _cleanup_provider_files(llm, attachments)
