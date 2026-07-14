from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.experiment import utc_now


class ModelCallUsage(Base):
    __tablename__ = "model_call_usages"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('actual_prompt','planning','validation','assessment','repair','structured_output_retry')",
            name="ck_model_call_usages_stage",
        ),
        CheckConstraint(
            "status IN ('response','response_without_usage','failed')",
            name="ck_model_call_usages_status",
        ),
        CheckConstraint("attempt >= 1", name="ck_model_call_usages_attempt"),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_model_call_usages_input_tokens_nonnegative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_model_call_usages_output_tokens_nonnegative",
        ),
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="ck_model_call_usages_total_tokens_nonnegative",
        ),
        CheckConstraint(
            "cached_content_tokens IS NULL OR cached_content_tokens >= 0",
            name="ck_model_call_usages_cached_content_tokens_nonnegative",
        ),
        CheckConstraint(
            "reasoning_tokens IS NULL OR reasoning_tokens >= 0",
            name="ck_model_call_usages_reasoning_tokens_nonnegative",
        ),
        UniqueConstraint("call_id", name="uq_model_call_usages_call_id"),
        Index("ix_model_call_usages_run_stage", "run_id", "stage"),
        Index(
            "uq_model_call_usages_provider_response_id",
            "provider_response_id",
            unique=True,
            postgresql_where=text("provider_response_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[str] = mapped_column(String(36), nullable=False)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    provider_response_id: Mapped[Optional[str]] = mapped_column(String)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cached_content_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    reasoning_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    extra_token_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    run: Mapped["Run"] = relationship(back_populates="model_call_usages")


from backend.models.run import Run  # noqa: E402,F401
