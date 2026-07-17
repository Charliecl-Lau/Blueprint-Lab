from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.experiment import Condition
from backend.models.run import Assessment, Run
from backend.models.source_document import RunSourceDocument, SourceDocument
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


def _create_run(db: Session, condition_id: int, source_bindings, model_settings: ModelSettings | None = None) -> Run:
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
                number = (db.scalar(select(func.max(Run.run_number)).where(Run.condition_id == condition_id)) or 0) + 1
                values = settings.model_dump(exclude_none=True)
                run = Run(
                    experiment_id=condition.experiment_id,
                    condition_id=condition.id,
                    run_number=number,
                    status="preparing_prompt",
                    model_settings=values,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    model_call_count=0,
                    **values,
                )
                db.add(run); db.flush()
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


def retry_run(db: Session, run_id: int) -> Run:
    original = db.get(Run, run_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Run not found")
    bindings = [_SnapshotBinding(source_document_id=item.source_document_id, role=item.role, ordinal=item.ordinal, included_text_hash=item.included_text_hash) for item in original.source_documents]
    return _create_run(db, original.condition_id, bindings, ModelSettings(**original.model_settings))


def retry_llm_evaluation(db: Session, assessment_id: int) -> Run:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    run = assessment.run
    if run.viewer_ready_at is None:
        raise HTTPException(
            status_code=409,
            detail="Assessment generation has not completed validation",
        )
    if run.status != "evaluation_failed":
        raise HTTPException(
            status_code=409,
            detail="LLM evaluation is not in a failed state",
        )

    run.status = "evaluating_quality"
    run.progress_message = "Preparing generated assessment for evaluation"
    run.error_type = None
    run.error_message = None
    run.completed_at = None
    db.commit()
    db.refresh(run)

    from backend.workers.evaluation_worker import run_llm_evaluation_pipeline

    run_llm_evaluation_pipeline.delay(run.id)
    return run
