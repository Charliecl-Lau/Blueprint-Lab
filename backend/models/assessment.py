from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Integer, String, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base
from backend.models.question import Question  # noqa: F401

class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("runs.id"), nullable=False)
    framework: Mapped[str] = mapped_column(String, nullable=False)
    control_set_id: Mapped[int] = mapped_column(Integer, ForeignKey("control_sets.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    run: Mapped["Run"] = relationship("Run", back_populates="assessments")
    control_set: Mapped["ControlSet"] = relationship("ControlSet", back_populates="assessments")
    prompt_generation: Mapped["PromptGeneration"] = relationship("PromptGeneration", back_populates="assessment", uselist=False)
    planner_output: Mapped["PlannerOutput"] = relationship("PlannerOutput", back_populates="assessment", uselist=False)
    assessment_generation: Mapped["AssessmentGeneration"] = relationship("AssessmentGeneration", back_populates="assessment", uselist=False)
    questions: Mapped[list["Question"]] = relationship("Question", back_populates="assessment")

class PromptGeneration(Base):
    __tablename__ = "prompt_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessments.id"), nullable=False)
    prompt_text: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="prompt_generation")

class PlannerOutput(Base):
    __tablename__ = "planner_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessments.id"), nullable=False)
    plan_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validation_errors: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="planner_output")

class AssessmentGeneration(Base):
    __tablename__ = "assessment_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessments.id"), nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="assessment_generation")
