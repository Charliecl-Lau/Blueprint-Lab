from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from backend.services.assessment_rubric import CRITERION_KEYS


CriterionKey = Literal[
    "technical_correctness",
    "course_alignment",
    "blooms_alignment",
    "clarity_solution",
    "materials_context",
]

RecommendedAction = Literal[
    "Accept without revision",
    "Accept with minor revision",
    "Revise before use",
    "Major revision required",
    "Reject assessment",
]


class LLMCriterionResult(BaseModel):
    criterion_key: CriterionKey
    score: int = Field(ge=1, le=5)
    justification: str = Field(min_length=1)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    suggested_improvements: list[str] = Field(default_factory=list)
    suggested_modifications: list[str] = Field(default_factory=list)


class LLMEvaluationResponse(BaseModel):
    criteria: list[LLMCriterionResult] = Field(min_length=5, max_length=5)
    major_strengths: list[str] = Field(default_factory=list)
    major_weaknesses: list[str] = Field(default_factory=list)
    highest_priority_revision: str = Field(min_length=1)
    recommended_instructor_action: RecommendedAction

    @model_validator(mode="after")
    def require_each_criterion_once(self):
        keys = [item.criterion_key for item in self.criteria]
        if set(keys) != set(CRITERION_KEYS) or len(keys) != len(set(keys)):
            raise ValueError("each rubric criterion must appear exactly once")
        return self


class HumanCriterionPatch(BaseModel):
    criterion_key: CriterionKey
    score: Optional[int] = Field(default=None, ge=1, le=5)
    comment: Optional[str] = None
    suggested_modification: Optional[str] = None
    issue_flags: Optional[list[str]] = None


class HumanEvaluationCreate(BaseModel):
    model_config = {"extra": "forbid"}


class HumanEvaluationPatch(BaseModel):
    revision: int = Field(ge=1)
    criteria: Optional[list[HumanCriterionPatch]] = None
    highest_priority_issue: Optional[str] = None
    overall_comments: Optional[str] = None
    recommended_action: Optional[RecommendedAction] = None
    model_config = {"extra": "forbid"}


class EvaluationCriterionDetail(BaseModel):
    criterion_key: CriterionKey
    score: Optional[int]
    comment: Optional[str] = None
    suggested_modification: Optional[str] = None
    issue_flags: list[str] = Field(default_factory=list)
    justification: Optional[str] = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    suggested_improvements: list[str] = Field(default_factory=list)
    suggested_modifications: list[str] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class EvaluationDetail(BaseModel):
    id: int
    assessment_id: int
    question_id: int
    evaluation_type: Literal["llm", "human"]
    evaluator_identity: str
    evaluation_model: Optional[str]
    evaluation_model_version: Optional[str]
    rubric_version: str
    rubric_snapshot: dict
    weighted_score: Optional[float]
    critical_gate: Optional[str]
    overall_decision: Optional[str]
    instructor_readiness: Optional[str]
    highest_priority_issue: Optional[str]
    highest_priority_revision: Optional[str]
    overall_comments: Optional[str]
    major_strengths: list[str]
    major_weaknesses: list[str]
    recommended_action: Optional[str]
    status: Literal["draft", "finalized", "failed", "reopened"]
    revision: int
    evaluation_timestamp: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    finalized_at: Optional[datetime]
    criteria: list[EvaluationCriterionDetail]
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class EvaluationAccessCreate(BaseModel):
    llm_evaluation_id: int


class EvaluationAccessDetail(BaseModel):
    first_opened_at: datetime
    opened_before_finalization: bool


class CriterionComparison(BaseModel):
    criterion_key: CriterionKey
    human_score: int
    llm_score: int
    difference: int
    absolute_difference: int
    indicator: Literal["agreement", "minor_difference", "significant_difference"]


class EvaluationComparison(BaseModel):
    criteria: list[CriterionComparison]
    mean_absolute_score_difference: float
    exact_agreement_rate: float
    agreement_within_one_point: float
    largest_disagreement: CriterionComparison
    human_weighted_score: float
    llm_weighted_score: float
    weighted_score_difference: float
    human_overall_decision: str
    llm_overall_decision: str
    decision_difference: bool


class GradingContext(BaseModel):
    experiment_id: int
    run_id: int
    assessment_id: int
    question_id: int
    question: dict
    rubric: dict
    llm_evaluation: EvaluationDetail
    human_evaluation: EvaluationDetail
    previous_question_id: Optional[int]
    next_question_id: Optional[int]
    viewer_path: str
