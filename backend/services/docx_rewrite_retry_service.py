from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import Assessment, DocxAuthoringAttempt, Run
from backend.services.docx_grounding import build_docx_grounding


class DocxRewriteRetryConflict(ValueError):
    """Raised when a run cannot begin a new rewrite-only cycle."""


def _lock_run(db: Session, run_id: int) -> Run | None:
    statement = select(Run).where(Run.id == run_id)
    if db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    return db.scalar(statement)


def request_docx_rewrite(
    db: Session,
    run_id: int,
    idempotency_key: str,
) -> tuple[Run | None, bool]:
    """Reserve one immutable rewrite cycle; return ``(run, should_enqueue)``."""
    run = _lock_run(db, run_id)
    if run is None:
        return None, False

    existing = db.scalar(
        select(DocxAuthoringAttempt).where(
            DocxAuthoringAttempt.run_id == run_id,
            DocxAuthoringAttempt.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return run, False

    original = db.scalar(
        select(Assessment).where(
            Assessment.run_id == run.id,
            Assessment.kind == "original_generation",
            Assessment.version == 1,
        )
    )
    if (
        run.status != "rewrite_failed"
        or original is None
        or original.parsed_json is None
        or run.canonical_assessment_id != original.id
    ):
        raise DocxRewriteRetryConflict(
            "Run is not eligible for a DOCX rewrite retry"
        )
    if run.reference_pdfs:
        raise DocxRewriteRetryConflict(
            "Upload-backed runs require a new run with fresh reference PDFs"
        )

    highest_cycle = db.scalar(
        select(func.max(DocxAuthoringAttempt.cycle_number)).where(
            DocxAuthoringAttempt.run_id == run.id
        )
    )
    grounding = build_docx_grounding(run)
    attempt = DocxAuthoringAttempt(
        run_id=run.id,
        source_assessment_id=original.id,
        cycle_number=(highest_cycle or 0) + 1,
        attempt_number=1,
        status="requested",
        provider=settings.llm_provider,
        model=settings.llm_model,
        prompt_hash=run.prompt.actual_prompt_hash,
        grounding_hash=grounding.sha256,
        idempotency_key=idempotency_key,
        envelope={},
        execution_report={},
        validation_report={},
    )
    db.add(attempt)
    run.status = "docx_authoring"
    run.progress_message = "Retrying the Word document rewrite"
    run.error_type = None
    run.error_message = None
    run.completed_at = None
    db.commit()
    return run, True
