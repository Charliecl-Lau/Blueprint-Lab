from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


PromptStructure = Literal["openai", "anthropic"]
AssessmentType = Literal["mcq", "short_answer", "mixed"]
CognitiveDemand = Literal[
    "remember_understand",
    "apply_analyze",
    "evaluate_create",
]


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

    @field_validator("*", mode="before")
    @classmethod
    def trim_optional_factor_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class ExperimentCreate(BaseModel):
    course: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    learning_objectives: str = Field(min_length=1)
    assessment_type: AssessmentType = "mixed"
    difficulty: str = Field(min_length=1)
    number_of_questions: int = Field(default=4, ge=1, le=50)
    estimated_time_minutes: int = Field(default=30, ge=1, le=480)
    cognitive_demand: CognitiveDemand = "remember_understand"
    additional_instruction: Optional[str] = Field(default=None, max_length=20000)
    prompt_structure: PromptStructure = "openai"
    factors: PromptFactors = Field(default_factory=PromptFactors)
    factor_inputs: PromptFactorInputs = Field(default_factory=PromptFactorInputs)

    @field_validator("course", "topic", "learning_objectives", mode="before")
    @classmethod
    def trim_required_assessment_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("additional_instruction", mode="before")
    @classmethod
    def trim_additional_instruction(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        return value or None

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
    run_number: int = 1
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    model_call_count: Optional[int] = None
    viewer_ready_at: Optional[datetime] = None
    progress_message: Optional[str] = None
    reference_pdf_filenames: list[str] = Field(default_factory=list)

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
    cognitive_demand: CognitiveDemand
    additional_instruction: Optional[str]
    created_at: datetime
    conditions: list[ConditionResponse]
    generations: list[GenerationSummary]
    runs: list[GenerationSummary]

    model_config = {"from_attributes": True}


class GenerationDetailResponse(GenerationSummary):
    generated_json: Optional[dict]
    condition: ConditionResponse
    prompt_text: Optional[str] = None
