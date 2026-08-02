from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.experiment import utc_now


class DocxAuthoringAttempt(Base):
    __tablename__ = "docx_authoring_attempts"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "cycle_number",
            "attempt_number",
            name="uq_docx_authoring_attempt_cycle",
        ),
        UniqueConstraint(
            "model_call_usage_id", name="uq_docx_authoring_attempt_usage"
        ),
        CheckConstraint(
            "cycle_number >= 1", name="ck_docx_authoring_cycle_positive"
        ),
        CheckConstraint(
            "attempt_number IN (1, 2)", name="ck_docx_authoring_attempt_bounded"
        ),
        CheckConstraint(
            "status IN ('requested','generated','executing','validating',"
            "'succeeded','failed')",
            name="ck_docx_authoring_status",
        ),
        CheckConstraint(
            "length(prompt_hash) = 64", name="ck_docx_authoring_prompt_hash"
        ),
        CheckConstraint(
            "length(grounding_hash) = 64", name="ck_docx_authoring_grounding_hash"
        ),
        CheckConstraint(
            "sandbox_image_digest IS NULL OR length(sandbox_image_digest) = 64",
            name="ck_docx_authoring_sandbox_digest",
        ),
        CheckConstraint(
            "idempotency_key IS NULL OR attempt_number = 1",
            name="ck_docx_authoring_idempotency_initial_only",
        ),
        CheckConstraint(
            "repairable = false OR failure_category IS NULL OR "
            "failure_category NOT IN ('hostile_code','security_violation')",
            name="ck_docx_authoring_security_not_repairable",
        ),
        ForeignKeyConstraint(
            ["source_assessment_id", "run_id"],
            ["assessments.id", "assessments.run_id"],
            name="fk_docx_authoring_source_same_run",
        ),
        Index(
            "uq_docx_authoring_run_idempotency",
            "run_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    source_assessment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    model_version: Mapped[Optional[str]] = mapped_column(String)
    provider_request_id: Mapped[Optional[str]] = mapped_column(String)
    model_call_usage_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("model_call_usages.id")
    )
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    grounding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128))
    program_text: Mapped[Optional[str]] = mapped_column(Text)
    envelope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    sandbox_image_digest: Mapped[Optional[str]] = mapped_column(String(64))
    execution_report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    validation_report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failure_category: Mapped[Optional[str]] = mapped_column(String)
    repairable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    run: Mapped["Run"] = relationship(
        back_populates="docx_authoring_attempts",
        foreign_keys=[run_id],
        overlaps="source_assessment,docx_authoring_attempts",
    )
    source_assessment: Mapped["Assessment"] = relationship(
        back_populates="docx_authoring_attempts",
        foreign_keys=[source_assessment_id, run_id],
        overlaps="run,docx_authoring_attempts",
    )
    model_call_usage: Mapped[Optional["ModelCallUsage"]] = relationship()


from backend.models.model_call_usage import ModelCallUsage  # noqa: E402,F401
from backend.models.run import Assessment, Run  # noqa: E402,F401
