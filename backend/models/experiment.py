from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (CheckConstraint("status IN ('draft','active','completed','archived')"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="Untitled experiment")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topic_area: Mapped[str] = mapped_column(String, nullable=False, default="Unspecified")
    research_question: Mapped[str] = mapped_column(Text, nullable=False, default="Unspecified")
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    course: Mapped[str] = mapped_column(String, nullable=False)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    learning_objectives: Mapped[str] = mapped_column(Text, nullable=False)
    assessment_type: Mapped[str] = mapped_column(String, nullable=False)
    difficulty: Mapped[str] = mapped_column(String, nullable=False)
    number_of_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    conditions: Mapped[list["Condition"]] = relationship(back_populates="experiment")
    runs: Mapped[list["Run"]] = relationship(back_populates="experiment")

    @property
    def generations(self):
        return self.runs


class Condition(Base):
    __tablename__ = "conditions"
    __table_args__ = (UniqueConstraint("experiment_id", "condition_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False)
    condition_code: Mapped[str] = mapped_column(String, nullable=False, default="C100")
    prompt_structure: Mapped[str] = mapped_column(String, nullable=False)
    concept_bridge_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    few_shot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reference_content_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reasoning_guidance_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bloom_level_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    factor_configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    factor_inputs: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    condition_label: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    experiment: Mapped[Experiment] = relationship(back_populates="conditions")
    runs: Mapped[list["Run"]] = relationship(back_populates="condition")

    @property
    def generations(self):
        return self.runs


# Imports at the bottom avoid circular model-module imports while preserving old imports.
from backend.models.run import (  # noqa: E402,F401
    Assessment,
    DocumentArtifact,
    Generation,
    Prompt,
    PromptRecord,
    RubricResult,
    Run,
)
