from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from backend.database import Base
from backend.models.experiment import utc_now


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("status IN ('pending','running','prompting','generating','documenting','completed','failed','complete','error')"),
        UniqueConstraint("condition_id", "run_number"),
        Index("ix_runs_experiment_id", "experiment_id"), Index("ix_runs_condition_id", "condition_id"),
        Index("ix_runs_status", "status"), Index("ix_runs_created_at", "created_at"),
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
    generated_json: Mapped[Optional[dict]] = mapped_column(JSON)
    request_id: Mapped[Optional[str]] = mapped_column(String)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    finish_reason: Mapped[Optional[str]] = mapped_column(String)
    error_type: Mapped[Optional[str]] = mapped_column(String)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    experiment: Mapped["Experiment"] = relationship(back_populates="runs")
    condition: Mapped["Condition"] = relationship(back_populates="runs")
    prompt: Mapped[Optional["Prompt"]] = relationship(back_populates="run", uselist=False, cascade="all, delete-orphan")
    assessment: Mapped[Optional["Assessment"]] = relationship(back_populates="run", uselist=False, cascade="all, delete-orphan")
    document_artifact: Mapped[Optional["DocumentArtifact"]] = relationship(back_populates="run", uselist=False)
    source_documents: Mapped[list["RunSourceDocument"]] = relationship(back_populates="run")
    rubric_results: Mapped[list["RubricResult"]] = relationship(back_populates="run")
    model_name = synonym("provider")
    model_version = synonym("version")
    generation_time_ms = synonym("duration_ms")
    prompt_record = synonym("prompt")


class Prompt(Base):
    __tablename__ = "prompts"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), unique=True, nullable=False)
    prompt_structure: Mapped[str] = mapped_column(String, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    final_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    template_version: Mapped[str] = mapped_column(String, nullable=False, default="legacy")
    generator_version: Mapped[str] = mapped_column(String, nullable=False, default="legacy")
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    run: Mapped[Run] = relationship(back_populates="prompt")
    generation_id = synonym("run_id")
    full_prompt = synonym("final_prompt")


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), unique=True, nullable=False)
    raw_response_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_json: Mapped[Optional[dict]] = mapped_column(JSON)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    run: Mapped[Run] = relationship(back_populates="assessment")


class DocumentArtifact(Base):
    __tablename__ = "document_artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
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
