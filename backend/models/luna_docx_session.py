from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.experiment import utc_now


class LunaDocxSession(Base):
    __tablename__ = "luna_docx_sessions"
    __table_args__ = (
        UniqueConstraint("run_id", "cycle_number", name="uq_luna_docx_session_cycle"),
        CheckConstraint("cycle_number >= 1", name="ck_luna_docx_session_cycle"),
        CheckConstraint("maximum_repairs >= 0", name="ck_luna_docx_session_max_repairs"),
        CheckConstraint("repair_count >= 0", name="ck_luna_docx_session_repairs"),
        CheckConstraint("attempt_count >= 0", name="ck_luna_docx_session_attempts"),
        CheckConstraint("attempt_count = 0 OR attempt_count = repair_count + 1", name="ck_luna_docx_session_counts"),
        CheckConstraint("status IN ('creating','authoring','validating','repairing','succeeded','failed')", name="ck_luna_docx_session_status"),
        CheckConstraint("outcome IS NULL OR outcome IN ('succeeded','failed')", name="ck_luna_docx_session_outcome"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    source_assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), nullable=False)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="creating")
    outcome: Mapped[Optional[str]] = mapped_column(String)
    container_id: Mapped[Optional[str]] = mapped_column(String)
    maximum_repairs: Mapped[int] = mapped_column(Integer, nullable=False)
    repair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_issue_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    final_artifact_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    failure_category: Mapped[Optional[str]] = mapped_column(String)
    cleanup_error_code: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    run: Mapped["Run"] = relationship(back_populates="luna_docx_sessions")
    source_assessment: Mapped["Assessment"] = relationship(foreign_keys=[source_assessment_id])
    attempts: Mapped[list["LunaDocxAttempt"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="LunaDocxAttempt.attempt_number"
    )


class LunaDocxAttempt(Base):
    __tablename__ = "luna_docx_attempts"
    __table_args__ = (
        UniqueConstraint("session_id", "attempt_number", name="uq_luna_docx_attempt_number"),
        UniqueConstraint("model_call_usage_id", name="uq_luna_docx_attempt_usage"),
        CheckConstraint("attempt_number >= 1", name="ck_luna_docx_attempt_number"),
        CheckConstraint("kind IN ('initial','repair')", name="ck_luna_docx_attempt_kind"),
        CheckConstraint("status IN ('requested','generated','validating','succeeded','failed')", name="ck_luna_docx_attempt_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("luna_docx_sessions.id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="requested")
    model_call_usage_id: Mapped[Optional[int]] = mapped_column(ForeignKey("model_call_usages.id"))
    provider_response_id: Mapped[Optional[str]] = mapped_column(String)
    prompt_hash: Mapped[Optional[str]] = mapped_column(String(64))
    input_artifact_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    output_artifact_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    issue_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    validation_report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    repair_feedback: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    provider_failure_code: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    session: Mapped[LunaDocxSession] = relationship(back_populates="attempts")
    model_call_usage: Mapped[Optional["ModelCallUsage"]] = relationship()


from backend.models.model_call_usage import ModelCallUsage  # noqa: E402,F401
from backend.models.run import Assessment, Run  # noqa: E402,F401
