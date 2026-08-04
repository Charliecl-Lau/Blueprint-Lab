"""Persistence for replayable agentic DOCX sessions."""

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.experiment import utc_now


class DocxToolSession(Base):
    __tablename__ = "docx_tool_sessions"
    __table_args__ = (
        UniqueConstraint("run_id", "cycle_number", name="uq_docx_tool_sessions_run_cycle"),
        UniqueConstraint("idempotency_key", name="uq_docx_tool_sessions_idempotency"),
        ForeignKeyConstraint(["source_assessment_id", "run_id"], ["assessments.id", "assessments.run_id"], name="fk_docx_tool_session_source_same_run"),
        CheckConstraint("cycle_number >= 1", name="ck_docx_tool_session_cycle"),
        CheckConstraint("workspace_revision >= 0", name="ck_docx_tool_session_revision"),
        CheckConstraint("maximum_revisions >= 0 AND maximum_revisions <= 10", name="ck_docx_tool_session_max_revisions"),
        CheckConstraint("status IN ('pending','designing','executing','validating','reviewing','succeeded','failed')", name="ck_docx_tool_session_status"),
        CheckConstraint("final_decision IS NULL OR final_decision IN ('approve','reject','budget_exhausted','machine_failed')", name="ck_docx_tool_session_decision"),
        CheckConstraint("length(content_catalog_hash) = 64", name="ck_docx_tool_session_catalog_hash"),
        CheckConstraint("length(design_contract_hash) = 64", name="ck_docx_tool_session_contract_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    source_assessment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    content_catalog_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    design_contract_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    initial_workspace_hash: Mapped[Optional[str]] = mapped_column(String(64))
    final_workspace_hash: Mapped[Optional[str]] = mapped_column(String(64))
    maximum_revisions: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    final_decision: Mapped[Optional[str]] = mapped_column(String)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    run: Mapped["Run"] = relationship(back_populates="docx_tool_sessions", foreign_keys=[run_id], overlaps="source_assessment,docx_tool_sessions")
    source_assessment: Mapped["Assessment"] = relationship(back_populates="docx_tool_sessions", foreign_keys=[source_assessment_id, run_id], overlaps="run,docx_tool_sessions")
    iterations: Mapped[list["DocxToolIteration"]] = relationship(back_populates="session", cascade="all, delete-orphan", order_by="DocxToolIteration.iteration_number")
    actions: Mapped[list["DocxToolAction"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class DocxToolIteration(Base):
    __tablename__ = "docx_tool_iterations"
    __table_args__ = (
        UniqueConstraint("session_id", "iteration_number", name="uq_docx_tool_iteration_number"),
        UniqueConstraint("model_call_usage_id", name="uq_docx_tool_iteration_usage"),
        CheckConstraint("iteration_number >= 0 AND iteration_number <= 10", name="ck_docx_tool_iteration_bounded"),
        CheckConstraint("kind IN ('design','visual_revision')", name="ck_docx_tool_iteration_kind"),
        CheckConstraint("review_decision IS NULL OR review_decision IN ('approve','revise','reject')", name="ck_docx_tool_iteration_review"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("docx_tool_sessions.id", ondelete="CASCADE"), nullable=False)
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    model_call_usage_id: Mapped[Optional[int]] = mapped_column(ForeignKey("model_call_usages.id"))
    input_workspace_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_workspace_hash: Mapped[Optional[str]] = mapped_column(String(64))
    draft_docx_hash: Mapped[Optional[str]] = mapped_column(String(64))
    draft_pdf_hash: Mapped[Optional[str]] = mapped_column(String(64))
    page_image_metadata: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    validator_report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    review_decision: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    session: Mapped[DocxToolSession] = relationship(back_populates="iterations")
    model_call_usage: Mapped[Optional["ModelCallUsage"]] = relationship()
    actions: Mapped[list["DocxToolAction"]] = relationship(back_populates="iteration", cascade="all, delete-orphan", order_by="DocxToolAction.sequence_number")


class DocxToolAction(Base):
    __tablename__ = "docx_tool_actions"
    __table_args__ = (
        UniqueConstraint("session_id", "operation_id", name="uq_docx_tool_action_operation"),
        UniqueConstraint("iteration_id", "sequence_number", name="uq_docx_tool_action_sequence"),
        CheckConstraint("sequence_number >= 0", name="ck_docx_tool_action_sequence"),
        CheckConstraint("status IN ('accepted','succeeded','failed')", name="ck_docx_tool_action_status"),
        CheckConstraint("duration_ms >= 0", name="ck_docx_tool_action_duration"),
        Index("ix_docx_tool_actions_session", "session_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("docx_tool_sessions.id", ondelete="CASCADE"), nullable=False)
    iteration_id: Mapped[int] = mapped_column(ForeignKey("docx_tool_iterations.id", ondelete="CASCADE"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    validated_arguments: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False)
    safe_error_code: Mapped[Optional[str]] = mapped_column(String(64))
    before_workspace_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    after_workspace_hash: Mapped[Optional[str]] = mapped_column(String(64))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    session: Mapped[DocxToolSession] = relationship(back_populates="actions")
    iteration: Mapped[DocxToolIteration] = relationship(back_populates="actions")


from backend.models.model_call_usage import ModelCallUsage  # noqa: E402,F401
from backend.models.run import Assessment, Run  # noqa: E402,F401
