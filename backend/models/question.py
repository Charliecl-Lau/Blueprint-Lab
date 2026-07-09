from sqlalchemy import Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base

class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessments.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)

    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="questions")
    options: Mapped[list["MCQOption"]] = relationship("MCQOption", back_populates="question")
    model_answer: Mapped["ModelAnswer"] = relationship("ModelAnswer", back_populates="question", uselist=False)

class MCQOption(Base):
    __tablename__ = "mcq_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)

    question: Mapped["Question"] = relationship("Question", back_populates="options")

class ModelAnswer(Base):
    __tablename__ = "model_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)

    question: Mapped["Question"] = relationship("Question", back_populates="model_answer")
