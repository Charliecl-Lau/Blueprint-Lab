from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field

class ControlSetCreate(BaseModel):
    personality: str
    prompt_length: str
    result_length: str
    action_word_count: int = Field(ge=1, le=5)

class RunCreate(BaseModel):
    topic: str
    expectations: str
    mcq_count: int = Field(default=10, ge=1)
    long_answer_count: int = Field(default=3, ge=1)
    control_sets: List[ControlSetCreate] = Field(min_length=4, max_length=4)
    frameworks: List[str] = Field(default_factory=lambda: ["forge", "openai", "risen"])

class ControlSetResponse(BaseModel):
    id: int
    personality: str
    prompt_length: str
    result_length: str
    action_word_count: int

    model_config = {"from_attributes": True}

class AssessmentSummary(BaseModel):
    id: int
    framework: str
    control_set_id: int
    status: str

    model_config = {"from_attributes": True}

class RunResponse(BaseModel):
    id: int
    topic: str
    expectations: str
    mcq_count: int
    long_answer_count: int
    created_at: datetime
    control_sets: List[ControlSetResponse]
    assessments: List[AssessmentSummary]

    model_config = {"from_attributes": True}

class MCQOptionDetail(BaseModel):
    id: int
    body: str
    is_correct: bool
    model_config = {"from_attributes": True}

class ModelAnswerDetail(BaseModel):
    body: str
    model_config = {"from_attributes": True}

class QuestionDetail(BaseModel):
    id: int
    type: Literal["mcq", "long_answer"]
    body: str
    order: int
    options: List[MCQOptionDetail]
    model_answer: Optional[ModelAnswerDetail]
    model_config = {"from_attributes": True, "protected_namespaces": ()}

class AssessmentDetailResponse(BaseModel):
    id: int
    framework: str
    control_set_id: int
    status: str
    created_at: datetime
    questions: List[QuestionDetail]
    model_config = {"from_attributes": True}
