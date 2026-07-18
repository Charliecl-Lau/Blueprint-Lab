from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.evaluation import Evaluation
from backend.models.experiment import Condition, utc_now
from backend.models.run import Assessment, Run, RunReferencePdf
from backend.models.source_document import RunSourceDocument, SourceDocument
from backend.services.assessment_rubric import RUBRIC_VERSION
from backend.schemas.run_schema import ModelSettings, SourceBinding


def _validate(bindings):
    keys = [(item.role, item.ordinal) for item in bindings]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate source binding role and ordinal")


@dataclass(frozen=True)
class _SnapshotBinding:
    source_document_id: int
    role: str
    ordinal: int
    included_text_hash: str


def create_run(db: Session, condition_id: int, source_bindings: list[SourceBinding], model_settings: ModelSettings | None = None) -> Run:
    return _create_run(db, condition_id, source_bindings, model_settings)


def _create_run(
    db: Session,
    condition_id: int,
    source_bindings,
    model_settings: ModelSettings | None = None,
    reference_pdf_filenames: Sequence[str] = (),
) -> Run:
    _validate(source_bindings)
    settings = model_settings or ModelSettings()
    for attempt in range(3):
        try:
            with db.begin_nested():
                statement = select(Condition).where(Condition.id == condition_id)
                if db.bind.dialect.name == "postgresql":
                    statement = statement.with_for_update()
                condition = db.execute(statement).scalar_one_or_none()
                if condition is None:
                    raise HTTPException(status_code=404, detail="Condition not found")
                legacy_reference_content = condition.factor_inputs.get(
                    "reference_content"
                )
                if (
                    condition.reference_content_enabled
                    and not legacy_reference_content
                    and not reference_pdf_filenames
                ):
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "reference_pdfs_required",
                            "message": (
                                "Use the PDF-aware experiment or retry endpoint and "
                                "upload fresh reference PDFs."
                            ),
                        },
                    )
                number = (db.scalar(select(func.max(Run.run_number)).where(Run.condition_id == condition_id)) or 0) + 1
                values = settings.model_dump(exclude_none=True)
                run = Run(
                    experiment_id=condition.experiment_id,
                    condition_id=condition.id,
                    run_number=number,
                    status="pending",
                    model_settings=values,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    model_call_count=0,
                    **values,
                )
                db.add(run); db.flush()
                run.reference_pdfs = [
                    RunReferencePdf(
                        ordinal=ordinal,
                        original_filename=filename,
                    )
                    for ordinal, filename in enumerate(reference_pdf_filenames)
                ]
                for binding in source_bindings:
                    source = db.get(SourceDocument, binding.source_document_id)
                    if source is None:
                        raise HTTPException(status_code=404, detail=f"Source document {binding.source_document_id} not found")
                    included = (source.extracted_text or "").encode() if source.extracted_text is not None else source.content
                    snapshot_hash = binding.included_text_hash if isinstance(binding, _SnapshotBinding) else hashlib.sha256(included).hexdigest()
                    db.add(RunSourceDocument(run_id=run.id, source_document_id=source.id, role=binding.role, ordinal=binding.ordinal, included_text_hash=snapshot_hash))
                db.flush()
            db.commit(); db.refresh(run)
            return run
        except IntegrityError:
            if attempt == 2:
                db.rollback()
                raise
        except Exception:
            db.rollback()
            raise
    raise RuntimeError("unreachable")


def mark_generation_dispatch_failed(db: Session, run: Run) -> None:
    run.status = "error"
    run.progress_message = "Assessment generation could not be queued"
    run.error_type = "generation_dispatch_error"
    run.error_message = "Assessment generation could not be queued. Retry the run."
    run.completed_at = utc_now()
    db.commit()


def retry_run(
    db: Session,
    run_id: int,
    reference_pdf_filenames: Sequence[str] | None = None,
) -> Run:
    original = db.get(Run, run_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Run not found")
    pdf_backed = bool(original.reference_pdfs)
    if pdf_backed and not reference_pdf_filenames:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "reference_pdfs_required",
                "message": "Upload fresh reference PDFs to retry this run.",
            },
        )
    if pdf_backed and len(reference_pdf_filenames) > 3:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "too_many_reference_pdfs",
                "message": "Upload no more than three reference PDFs.",
            },
        )
    if not pdf_backed and reference_pdf_filenames is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "reference_pdfs_not_allowed",
                "message": "This run was not created with reference PDFs.",
            },
        )
    bindings = [_SnapshotBinding(source_document_id=item.source_document_id, role=item.role, ordinal=item.ordinal, included_text_hash=item.included_text_hash) for item in original.source_documents]
    return _create_run(
        db,
        original.condition_id,
        bindings,
        ModelSettings(**original.model_settings),
        reference_pdf_filenames or (),
    )


def retry_llm_evaluation(db: Session, assessment_id: int) -> Run:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    run = assessment.run
    if (
        run.status != "complete"
        or assessment.parsed_json is None
        or run.document_artifact is None
    ):
        raise HTTPException(
            status_code=409,
            detail="Assessment generation has not completed",
        )
    from backend.services.assessment_evaluation import persist_assessment_questions

    questions = persist_assessment_questions(db, assessment)
    evaluation_model = settings.llm_evaluation_model or settings.llm_model
    current_evaluations = db.scalars(
        select(Evaluation).where(
            Evaluation.assessment_id == assessment.id,
            Evaluation.evaluation_type == "llm",
            Evaluation.evaluator_identity == evaluation_model,
            Evaluation.rubric_version == RUBRIC_VERSION,
        )
    ).all()
    finalized_question_ids = {
        item.question_id
        for item in current_evaluations
        if item.status == "finalized"
    }
    if questions and all(
        question.id in finalized_question_ids for question in questions
    ):
        raise HTTPException(
            status_code=409,
            detail="LLM evaluation is already complete",
        )
    if any(item.status in {"draft", "reopened"} for item in current_evaluations):
        raise HTTPException(
            status_code=409,
            detail="LLM evaluation is already in progress",
        )

    db.commit()
    db.refresh(run)

    from backend.workers.evaluation_worker import run_llm_evaluation_pipeline

    run_llm_evaluation_pipeline.delay(run.id)
    return run
