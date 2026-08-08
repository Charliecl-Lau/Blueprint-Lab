from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.experiment import utc_now


class AssessmentRepairAttempt(Base):
    __tablename__ = "assessment_repair_attempts"
    __table_args__ = (
        CheckConstraint("question_ordinal >= 0", name="ck_assessment_repair_question"),
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_assessment_repair_attempt_number",
        ),
        CheckConstraint(
            "status IN ('pending','response','invalid','merged')",
            name="ck_assessment_repair_status",
        ),
        Index("ix_assessment_repair_run_attempt", "run_id", "attempt_number"),
        Index("ix_assessment_repair_validator_code", "validator_code"),
        Index("ix_assessment_repair_target_section", "target_section"),
        Index("ix_assessment_repair_success", "success"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    assessment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assessments.id"))
    model_call_usage_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("model_call_usages.id"), nullable=True
    )
    question_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    issues: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    repair_type: Mapped[str] = mapped_column(String, nullable=False, default="structural")
    error_type: Mapped[Optional[str]] = mapped_column(String)
    validator_code: Mapped[Optional[str]] = mapped_column(String)
    validator_message: Mapped[Optional[str]] = mapped_column(Text)
    target_path: Mapped[Optional[str]] = mapped_column(String)
    target_section: Mapped[Optional[str]] = mapped_column(String)
    question_id: Mapped[Optional[str]] = mapped_column(String)
    solution_id: Mapped[Optional[str]] = mapped_column(String)
    equation_id: Mapped[Optional[str]] = mapped_column(String)
    repair_scope: Mapped[Optional[str]] = mapped_column(String)
    before_content: Mapped[Optional[dict]] = mapped_column(JSON)
    after_content: Mapped[Optional[dict]] = mapped_column(JSON)
    before_hash: Mapped[Optional[str]] = mapped_column(String(64))
    after_hash: Mapped[Optional[str]] = mapped_column(String(64))
    model: Mapped[Optional[str]] = mapped_column(String)
    model_call_id: Mapped[Optional[str]] = mapped_column(String)
    prompt_version: Mapped[Optional[str]] = mapped_column(String)
    token_usage: Mapped[Optional[dict]] = mapped_column(JSON)
    success: Mapped[Optional[bool]] = mapped_column(Boolean)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    run: Mapped["Run"] = relationship(back_populates="assessment_repair_attempts")
    model_call_usage: Mapped[Optional["ModelCallUsage"]] = relationship()


from backend.models.model_call_usage import ModelCallUsage  # noqa: E402,F401
from backend.models.run import Run  # noqa: E402,F401
