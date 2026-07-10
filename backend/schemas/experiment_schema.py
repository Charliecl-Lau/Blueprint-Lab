from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


PromptStructure = Literal["openai", "anthropic"]
AssessmentType = Literal["mcq", "short_answer", "mixed"]


class PromptFactors(BaseModel):
    concept_bridge: bool = False
    few_shot: bool = False
    reference_content: bool = False
    reasoning_guidance: bool = False


class PromptFactorInputs(BaseModel):
    concept_bridge: Optional[str] = Field(default=None, max_length=20000)
    few_shot: Optional[str] = Field(default=None, max_length=20000)
    reference_content: Optional[str] = Field(default=None, max_length=20000)
    reasoning_guidance: Optional[str] = Field(default=None, max_length=20000)


class ExperimentCreate(BaseModel):
    course: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    learning_objectives: str = Field(min_length=1)
    assessment_type: AssessmentType = "mixed"
    difficulty: str = Field(min_length=1)
    number_of_questions: int = Field(default=4, ge=1, le=50)
    estimated_time_minutes: int = Field(default=30, ge=1, le=480)
    prompt_structure: PromptStructure = "openai"
    factors: PromptFactors = Field(default_factory=PromptFactors)
    factor_inputs: PromptFactorInputs = Field(default_factory=PromptFactorInputs)

    @model_validator(mode="after")
    def require_enabled_factor_content(self):
        for name, enabled in self.factors.model_dump().items():
            value = getattr(self.factor_inputs, name)
            if enabled and (value is None or not value.strip()):
                raise ValueError(f"Enabled factor '{name}' requires content")
        return self


class ConditionResponse(BaseModel):
    id: int
    prompt_structure: PromptStructure
    concept_bridge_enabled: bool
    few_shot_enabled: bool
    reference_content_enabled: bool
    reasoning_guidance_enabled: bool
    factor_inputs: dict
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
    estimated_time_minutes: int
    created_at: datetime
    conditions: list[ConditionResponse]
    generations: list[GenerationSummary]

    model_config = {"from_attributes": True}


class GenerationDetailResponse(GenerationSummary):
    generated_json: Optional[dict]
    condition: ConditionResponse
    prompt_text: Optional[str] = None
