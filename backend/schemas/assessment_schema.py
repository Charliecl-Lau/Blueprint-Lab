from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class MCQOptionSchema(BaseModel):
    body: str
    is_correct: bool


class QuestionMetadata(BaseModel):
    prompt_template_id: str = "Not Assigned"
    actual_prompt_id: str = "Not Assigned"
    output_id: str = "Not Assigned"
    final_question_id: str = "Not Assigned"
    question_title: str = ""
    difficulty_level: str = ""
    intended_assessment_setting: str = ""
    mse202_concepts: List[str] = Field(default_factory=list)
    mse302_concepts: List[str] = Field(default_factory=list)
    concept_map_bridge: str = ""
    materials_science_context: str = ""
    estimated_time: str = ""
    learning_objectives: List[str] = Field(default_factory=list)
    id_requirements: str = ""


class EquationSchema(BaseModel):
    label: str
    expression: str
    location: Literal["question", "solution"]


class QualityCheckSchema(BaseModel):
    criterion: str
    rating: int = Field(ge=1, le=5)
    comment: str


class QuestionResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    type: Literal["mcq", "short_answer", "long_answer"]
    metadata: QuestionMetadata = Field(default_factory=QuestionMetadata)
    body: str
    options: List[MCQOptionSchema] = Field(default_factory=list)
    model_answer: Optional[str] = None
    equations: List[EquationSchema] = Field(default_factory=list)
    quality_check: List[QualityCheckSchema] = Field(default_factory=list)
    revision_options: List[str] = Field(default_factory=list)


class AssessmentGenerationResponse(BaseModel):
    questions: List[QuestionResponse]
