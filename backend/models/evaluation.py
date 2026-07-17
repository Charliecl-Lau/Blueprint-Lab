from copy import deepcopy
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.experiment import utc_now


CRITERION_KEY_SQL = (
    "'technical_correctness','course_alignment','blooms_alignment',"
    "'clarity_solution','materials_context'"
)


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "ordinal",
            name="uq_assessment_questions_ordinal",
        ),
        Index(
            "ix_assessment_questions_content_hash",
            "assessment_id",
            "content_hash",
        ),
        CheckConstraint("ordinal >= 0", name="ck_assessment_questions_ordinal"),
        CheckConstraint(
            "assessment_version >= 1",
            name="ck_assessment_questions_version",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_assessment_questions_content_hash",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    assessment_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    assessment: Mapped["Assessment"] = relationship(back_populates="questions")
    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        CheckConstraint(
            "evaluation_type IN ('llm','human')",
            name="ck_evaluations_type",
        ),
        CheckConstraint(
            "status IN ('draft','finalized','failed','reopened')",
            name="ck_evaluations_status",
        ),
        CheckConstraint("attempt >= 1", name="ck_evaluations_attempt"),
        CheckConstraint("revision >= 1", name="ck_evaluations_revision"),
        CheckConstraint(
            "weighted_score IS NULL OR (weighted_score >= 0 AND weighted_score <= 100)",
            name="ck_evaluations_weighted_score",
        ),
        CheckConstraint(
            "assessment_version >= 1",
            name="ck_evaluations_assessment_version",
        ),
        CheckConstraint(
            "length(assessment_content_hash) = 64",
            name="ck_evaluations_assessment_content_hash",
        ),
        UniqueConstraint(
            "question_id",
            "evaluation_type",
            "evaluator_identity",
            "attempt",
            name="uq_evaluation_attempt",
        ),
        Index(
            "ix_evaluations_question_type",
            "question_id",
            "evaluation_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id"), nullable=False
    )
    condition_id: Mapped[int] = mapped_column(
        ForeignKey("conditions.id"), nullable=False
    )
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id"), nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("assessment_questions.id"), nullable=False
    )
    assessment_version: Mapped[int] = mapped_column(Integer, nullable=False)
    assessment_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_type: Mapped[str] = mapped_column(String, nullable=False)
    evaluator_identity: Mapped[str] = mapped_column(String, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    evaluation_model: Mapped[Optional[str]] = mapped_column(String)
    evaluation_model_version: Mapped[Optional[str]] = mapped_column(String)
    rubric_version: Mapped[str] = mapped_column(String, nullable=False)
    rubric_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    prompt_template_id: Mapped[Optional[str]] = mapped_column(String)
    actual_prompt_id: Mapped[Optional[str]] = mapped_column(String)
    output_id: Mapped[Optional[str]] = mapped_column(String)
    generation_model: Mapped[Optional[str]] = mapped_column(String)
    generation_model_version: Mapped[Optional[str]] = mapped_column(String)
    prompt_design_factors: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    weighted_score: Mapped[Optional[float]] = mapped_column(Float)
    critical_gate: Mapped[Optional[str]] = mapped_column(String)
    overall_decision: Mapped[Optional[str]] = mapped_column(String)
    instructor_readiness: Mapped[Optional[str]] = mapped_column(String)
    highest_priority_issue: Mapped[Optional[str]] = mapped_column(Text)
    highest_priority_revision: Mapped[Optional[str]] = mapped_column(Text)
    overall_comments: Mapped[Optional[str]] = mapped_column(Text)
    major_strengths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    major_weaknesses: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recommended_action: Mapped[Optional[str]] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    evaluation_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    question: Mapped[AssessmentQuestion] = relationship(back_populates="evaluations")
    criteria: Mapped[list["EvaluationCriterion"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    revisions: Mapped[list["EvaluationRevision"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )
    llm_access_events: Mapped[list["EvaluationAccessEvent"]] = relationship(
        back_populates="human_evaluation",
        foreign_keys="EvaluationAccessEvent.human_evaluation_id",
        cascade="all, delete-orphan",
    )
    llm_disclosure_events: Mapped[list["EvaluationAccessEvent"]] = relationship(
        back_populates="llm_evaluation",
        foreign_keys="EvaluationAccessEvent.llm_evaluation_id",
    )

    @classmethod
    def from_run(
        cls,
        run: "Run",
        *,
        question: AssessmentQuestion,
        evaluation_type: str,
        evaluator_identity: str,
        rubric_version: str,
        rubric_snapshot: dict,
        evaluation_model: Optional[str] = None,
        attempt: int = 1,
    ) -> "Evaluation":
        prompt = run.prompt
        assessment = run.assessment
        condition = run.condition
        if assessment is None:
            raise ValueError("run must have a saved assessment before evaluation")

        return cls(
            experiment_id=run.experiment_id,
            condition_id=run.condition_id,
            run_id=run.id,
            assessment_id=assessment.id,
            question=question,
            assessment_version=question.assessment_version,
            assessment_content_hash=question.content_hash,
            evaluation_type=evaluation_type,
            evaluator_identity=evaluator_identity,
            attempt=attempt,
            evaluation_model=evaluation_model,
            rubric_version=rubric_version,
            rubric_snapshot=deepcopy(rubric_snapshot),
            prompt_template_id=(
                prompt.structure_prompt_version if prompt is not None else None
            ),
            actual_prompt_id=str(prompt.id) if prompt is not None else None,
            output_id=str(assessment.id),
            generation_model=run.model,
            generation_model_version=run.version,
            prompt_design_factors={
                "configuration": deepcopy(condition.factor_configuration),
                "inputs": deepcopy(condition.factor_inputs),
            },
        )


class EvaluationCriterion(Base):
    __tablename__ = "evaluation_criteria"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_id",
            "criterion_key",
            name="uq_evaluation_criteria_key",
        ),
        CheckConstraint(
            f"criterion_key IN ({CRITERION_KEY_SQL})",
            name="ck_evaluation_criteria_key",
        ),
        CheckConstraint(
            "score IS NULL OR (score >= 1 AND score <= 5)",
            name="ck_evaluation_criteria_score",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id"), nullable=False
    )
    criterion_key: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[Optional[int]] = mapped_column(Integer)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    suggested_modification: Mapped[Optional[str]] = mapped_column(Text)
    issue_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    justification: Mapped[Optional[str]] = mapped_column(Text)
    strengths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    weaknesses: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    suggested_improvements: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    suggested_modifications: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )

    evaluation: Mapped[Evaluation] = relationship(back_populates="criteria")


class EvaluationRevision(Base):
    __tablename__ = "evaluation_revisions"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_id", "revision", name="uq_evaluation_revisions_revision"
        ),
        CheckConstraint("revision >= 1", name="ck_evaluation_revisions_revision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    evaluation: Mapped[Evaluation] = relationship(back_populates="revisions")


class EvaluationAccessEvent(Base):
    __tablename__ = "evaluation_access_events"
    __table_args__ = (
        UniqueConstraint(
            "human_evaluation_id",
            "llm_evaluation_id",
            "reviewer_id",
            name="uq_evaluation_first_access",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    human_evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id"), nullable=False
    )
    llm_evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id"), nullable=False
    )
    reviewer_id: Mapped[str] = mapped_column(String, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    opened_before_finalization: Mapped[bool] = mapped_column(Boolean, nullable=False)

    human_evaluation: Mapped[Evaluation] = relationship(
        back_populates="llm_access_events",
        foreign_keys=[human_evaluation_id],
    )
    llm_evaluation: Mapped[Evaluation] = relationship(
        back_populates="llm_disclosure_events",
        foreign_keys=[llm_evaluation_id],
    )


from backend.models.run import Assessment, Run  # noqa: E402,F401
