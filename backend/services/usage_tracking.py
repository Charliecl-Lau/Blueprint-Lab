from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import ModelCallUsage, Run
from backend.models.experiment import utc_now
from backend.services.llm_client import LLMResult


def _existing_call(
    db: Session,
    *,
    call_id: str,
    provider_response_id: Optional[str],
) -> Optional[ModelCallUsage]:
    existing = db.scalar(
        select(ModelCallUsage).where(ModelCallUsage.call_id == call_id)
    )
    if existing is not None:
        return existing
    if provider_response_id is None:
        return None
    return db.scalar(
        select(ModelCallUsage).where(
            ModelCallUsage.provider_response_id == provider_response_id
        )
    )


def record_model_call(
    db: Session,
    *,
    run: Run,
    call_id: str,
    stage: str,
    attempt: int,
    result: Optional[LLMResult] = None,
    failed: bool = False,
) -> ModelCallUsage:
    """Persist one provider request and atomically update its run aggregates."""

    provider_response_id = result.provider_request_id if result is not None else None
    existing = _existing_call(
        db,
        call_id=call_id,
        provider_response_id=provider_response_id,
    )
    if existing is not None:
        return existing

    token_usage = result.usage if result is not None else None
    if result is None:
        status = "failed"
    elif token_usage is None:
        status = "response_without_usage"
    else:
        status = "response"

    usage = ModelCallUsage(
        call_id=call_id,
        run_id=run.id,
        stage=stage,
        attempt=attempt,
        status=status,
        provider_response_id=provider_response_id,
        input_tokens=token_usage.input_tokens if token_usage is not None else None,
        output_tokens=token_usage.output_tokens if token_usage is not None else None,
        total_tokens=token_usage.total_tokens if token_usage is not None else None,
        cached_content_tokens=(
            token_usage.cached_content_tokens if token_usage is not None else None
        ),
        reasoning_tokens=(token_usage.reasoning_tokens if token_usage is not None else None),
        extra_token_counts=(
            dict(token_usage.extra_token_counts) if token_usage is not None else {}
        ),
        responded_at=utc_now() if result is not None else None,
    )

    try:
        with db.begin_nested():
            db.add(usage)
            db.flush()
            locked_run = db.execute(
                select(Run).where(Run.id == run.id).with_for_update()
            ).scalar_one()
            locked_run.model_call_count = (locked_run.model_call_count or 0) + 1
            for aggregate_name in ("input_tokens", "output_tokens", "total_tokens"):
                reported_value = getattr(usage, aggregate_name)
                if reported_value is not None:
                    setattr(
                        locked_run,
                        aggregate_name,
                        (getattr(locked_run, aggregate_name) or 0) + reported_value,
                    )
        db.commit()
        return usage
    except IntegrityError:
        db.rollback()
        winner = _existing_call(
            db,
            call_id=call_id,
            provider_response_id=provider_response_id,
        )
        if winner is None:
            raise
        return winner
