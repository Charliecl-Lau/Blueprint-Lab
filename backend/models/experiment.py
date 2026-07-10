from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course: Mapped[str] = mapped_column(String, nullable=False)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    learning_objectives: Mapped[str] = mapped_column(String, nullable=False)
    assessment_type: Mapped[str] = mapped_column(String, nullable=False)
    difficulty: Mapped[str] = mapped_column(String, nullable=False)
    number_of_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    conditions: Mapped[list["Condition"]] = relationship("Condition", back_populates="experiment")
    generations: Mapped[list["Generation"]] = relationship("Generation", back_populates="experiment")


class Condition(Base):
    __tablename__ = "conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[int] = mapped_column(Integer, ForeignKey("experiments.id"), nullable=False)
    prompt_structure: Mapped[str] = mapped_column(String, nullable=False)
    concept_bridge_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    few_shot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reference_content_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reasoning_guidance_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    factor_inputs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    condition_label: Mapped[str] = mapped_column(String, nullable=False)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="conditions")
    generations: Mapped[list["Generation"]] = relationship("Generation", back_populates="condition")


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[int] = mapped_column(Integer, ForeignKey("experiments.id"), nullable=False)
    condition_id: Mapped[int] = mapped_column(Integer, ForeignKey("conditions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    model_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    generation_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    generated_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="generations")
    condition: Mapped["Condition"] = relationship("Condition", back_populates="generations")
    prompt_record: Mapped["PromptRecord"] = relationship(
        "PromptRecord", back_populates="generation", uselist=False
    )
    document_artifact: Mapped["DocumentArtifact"] = relationship(
        "DocumentArtifact", back_populates="generation", uselist=False
    )
    rubric_results: Mapped[list["RubricResult"]] = relationship(
        "RubricResult", back_populates="generation"
    )


class PromptRecord(Base):
    __tablename__ = "prompt_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generation_id: Mapped[int] = mapped_column(Integer, ForeignKey("generations.id"), nullable=False)
    prompt_structure: Mapped[str] = mapped_column(String, nullable=False)
    full_prompt: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    generation: Mapped["Generation"] = relationship("Generation", back_populates="prompt_record")


class DocumentArtifact(Base):
    __tablename__ = "document_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generation_id: Mapped[int] = mapped_column(Integer, ForeignKey("generations.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    generation: Mapped["Generation"] = relationship("Generation", back_populates="document_artifact")


class RubricResult(Base):
    __tablename__ = "rubric_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generation_id: Mapped[int] = mapped_column(Integer, ForeignKey("generations.id"), nullable=False)
    reviewer: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rubric_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    comments: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    generation: Mapped["Generation"] = relationship("Generation", back_populates="rubric_results")
