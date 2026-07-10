from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


PromptStructure = Literal["openai", "anthropic"]
AssessmentType = Literal["mcq", "short_answer", "mixed"]


class PromptFactors(BaseModel):
    course_bridge: bool = False
    few_shot: bool = False
    documents: bool = False


class ExperimentCreate(BaseModel):
    course: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    learning_objectives: str = Field(min_length=1)
    assessment_type: AssessmentType = "mixed"
    difficulty: str = Field(min_length=1)
    number_of_questions: int = Field(default=4, ge=1, le=50)
    prompt_structure: PromptStructure = "openai"
    factors: PromptFactors = Field(default_factory=PromptFactors)


class ConditionResponse(BaseModel):
    id: int
    prompt_structure: PromptStructure
    course_bridge_enabled: bool
    few_shot_enabled: bool
    documents_enabled: bool
    condition_label: str

    model_config = {"from_attributes": True}


class GenerationSummary(BaseModel):
    id: int
    condition_id: int
    status: str
    model_name: Optional[str]
    model_version: Optional[str]
    generation_time_ms: Optional[int]

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ExperimentResponse(BaseModel):
    id: int
    course: str
    topic: str
    learning_objectives: str
    assessment_type: str
    difficulty: str
    number_of_questions: int
    created_at: datetime
    conditions: list[ConditionResponse]
    generations: list[GenerationSummary]

    model_config = {"from_attributes": True}


class GenerationDetailResponse(GenerationSummary):
    generated_json: Optional[dict]
    condition: ConditionResponse
    prompt_text: Optional[str] = None
