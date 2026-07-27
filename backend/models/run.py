import hashlib
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from backend.database import Base
from backend.models.experiment import utc_now


def _actual_prompt_hash_default(context) -> str:
    value = context.get_current_parameters().get("actual_prompt", "")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _generation_envelope_hash_default(context) -> str:
    value = context.get_current_parameters().get("actual_prompt", "")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_content_default(context) -> str:
    value = context.get_current_parameters().get("content", b"")
    return hashlib.sha256(value).hexdigest()


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','prompting','generating','documenting','complete',"
            "'complete_with_warnings','error')",
            name="ck_runs_status",
        ),
        UniqueConstraint("condition_id", "run_number"),
        Index("ix_runs_experiment_id", "experiment_id"),
        Index("ix_runs_condition_id", "condition_id"),
        Index("ix_runs_status", "status"),
        Index("ix_runs_created_at", "created_at"),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_runs_input_tokens_nonnegative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_runs_output_tokens_nonnegative",
        ),
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="ck_runs_total_tokens_nonnegative",
        ),
        CheckConstraint(
            "model_call_count IS NULL OR model_call_count >= 0",
            name="ck_runs_model_call_count_nonnegative",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False)
    condition_id: Mapped[int] = mapped_column(ForeignKey("conditions.id"), nullable=False)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    provider: Mapped[Optional[str]] = mapped_column(String)
    model: Mapped[Optional[str]] = mapped_column(String)
    version: Mapped[Optional[str]] = mapped_column(String)
    temperature: Mapped[Optional[float]] = mapped_column(Float)
    top_p: Mapped[Optional[float]] = mapped_column(Float)
    seed: Mapped[Optional[int]] = mapped_column(Integer)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    model_settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    execution_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    request_id: Mapped[Optional[str]] = mapped_column(String)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    finish_reason: Mapped[Optional[str]] = mapped_column(String)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    model_call_count: Mapped[Optional[int]] = mapped_column(Integer)
    error_type: Mapped[Optional[str]] = mapped_column(String)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    viewer_ready_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    progress_message: Mapped[Optional[str]] = mapped_column(Text)
    experiment: Mapped["Experiment"] = relationship(back_populates="runs")
    condition: Mapped["Condition"] = relationship(back_populates="runs")
    prompt: Mapped[Optional["Prompt"]] = relationship(back_populates="run", uselist=False, cascade="all, delete-orphan")
    assessment: Mapped[Optional["Assessment"]] = relationship(back_populates="run", uselist=False, cascade="all, delete-orphan")
    document_artifact: Mapped[Optional["DocumentArtifact"]] = relationship(back_populates="run", uselist=False)
    source_documents: Mapped[list["RunSourceDocument"]] = relationship(back_populates="run")
    rubric_results: Mapped[list["RubricResult"]] = relationship(back_populates="run")
    model_call_usages: Mapped[list["ModelCallUsage"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    reference_pdfs: Mapped[list["RunReferencePdf"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RunReferencePdf.ordinal",
    )
    model_name = synonym("model")
    model_version = synonym("version")
    generation_time_ms = synonym("duration_ms")
    prompt_record = synonym("prompt")

    @property
    def reference_pdf_filenames(self) -> list[str]:
        return [item.original_filename for item in self.reference_pdfs]

    @property
    def generated_json(self) -> Optional[dict]:
        """Deprecated compatibility view; assessments.parsed_json is canonical."""
        return self.assessment.parsed_json if self.assessment is not None else None


class RunReferencePdf(Base):
    __tablename__ = "run_reference_pdfs"
    __table_args__ = (
        CheckConstraint(
            "ordinal >= 0 AND ordinal <= 2",
            name="ck_run_reference_pdfs_ordinal",
        ),
        UniqueConstraint(
            "run_id",
            "ordinal",
            name="uq_run_reference_pdfs_run_ordinal",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    run: Mapped[Run] = relationship(back_populates="reference_pdfs")


class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = (
        CheckConstraint("length(actual_prompt_hash) = 64"),
        CheckConstraint("length(generation_envelope_hash) = 64"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), unique=True, nullable=False)
    prompt_structure: Mapped[str] = mapped_column(String, nullable=False)
    structure_system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structure_input: Mapped[str] = mapped_column(Text, nullable=False, default="")
    actual_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    actual_prompt_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default=_actual_prompt_hash_default
    )
    structure_prompt_version: Mapped[str] = mapped_column(
        String, nullable=False, default="legacy"
    )
    actual_prompt_generator_version: Mapped[str] = mapped_column(
        String, nullable=False, default="legacy"
    )
    structure_request_id: Mapped[Optional[str]] = mapped_column(String)
    structure_model: Mapped[Optional[str]] = mapped_column(String)
    structure_model_version: Mapped[Optional[str]] = mapped_column(String)
    structure_finish_reason: Mapped[Optional[str]] = mapped_column(String)
    structure_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    generation_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    execution_system_prompt: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    execution_user_message: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    execution_schema_version: Mapped[str] = mapped_column(
        String, nullable=False, default="legacy"
    )
    generation_envelope_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default=_generation_envelope_hash_default
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    run: Mapped[Run] = relationship(back_populates="prompt")
    generation_id = synonym("run_id")
    system_prompt = synonym("structure_system_prompt")
    final_prompt = synonym("actual_prompt")
    template_version = synonym("structure_prompt_version")
    generator_version = synonym("actual_prompt_generator_version")
    prompt_hash = synonym("actual_prompt_hash")
    full_prompt = synonym("actual_prompt")


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("length(output_hash) = 64"),
        CheckConstraint(
            "validation_status IN ('valid','warning','invalid')",
            name="ck_assessments_validation_status",
        ),
        CheckConstraint(
            "parsed_json_hash IS NULL OR length(parsed_json_hash) = 64",
            name="ck_assessments_parsed_json_hash",
        ),
        CheckConstraint(
            "defects_accepted_at IS NULL OR validation_status = 'warning'",
            name="ck_assessments_warning_acceptance",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), unique=True, nullable=False)
    raw_response_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_json: Mapped[Optional[dict]] = mapped_column(JSON)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String, nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String, nullable=False, default="valid"
    )
    validation_issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recovery_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    parsed_json_hash: Mapped[Optional[str]] = mapped_column(String(64))
    defects_accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    defects_accepted_by: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    run: Mapped[Run] = relationship(back_populates="assessment")
    questions: Mapped[list["AssessmentQuestion"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class DocumentArtifact(Base):
    __tablename__ = "document_artifacts"
    __table_args__ = (CheckConstraint("length(content_hash) = 64"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, default=_hash_content_default
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    run: Mapped[Run] = relationship(back_populates="document_artifact")
    generation_id = synonym("run_id")
    generation = synonym("run")


class RubricResult(Base):
    __tablename__ = "rubric_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    generation_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    reviewer: Mapped[Optional[str]] = mapped_column(String)
    rubric_score: Mapped[Optional[float]] = mapped_column(Float)
    comments: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    run: Mapped[Run] = relationship(back_populates="rubric_results")
    generation = synonym("run")


Generation = Run
PromptRecord = Prompt

from backend.models.source_document import RunSourceDocument  # noqa: E402,F401
from backend.models.model_call_usage import ModelCallUsage  # noqa: E402,F401
