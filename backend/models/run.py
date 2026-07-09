from datetime import datetime, timezone
from sqlalchemy import Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base
from backend.models.assessment import Assessment  # noqa: F401

class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    expectations: Mapped[str] = mapped_column(String, nullable=False)
    mcq_count: Mapped[int] = mapped_column(Integer, default=10)
    long_answer_count: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    control_sets: Mapped[list["ControlSet"]] = relationship("ControlSet", back_populates="run")
    assessments: Mapped[list["Assessment"]] = relationship("Assessment", back_populates="run")

class ControlSet(Base):
    __tablename__ = "control_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("runs.id"), nullable=False)
    personality: Mapped[str] = mapped_column(String, nullable=False)
    prompt_length: Mapped[str] = mapped_column(String, nullable=False)
    result_length: Mapped[str] = mapped_column(String, nullable=False)
    action_word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    run: Mapped["Run"] = relationship("Run", back_populates="control_sets")
    assessments: Mapped[list["Assessment"]] = relationship("Assessment", back_populates="control_set")
