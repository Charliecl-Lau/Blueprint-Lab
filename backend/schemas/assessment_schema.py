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
    question_title: str
    question_type: Literal["mcq", "short_answer", "long_answer"]
    difficulty_level: str
    intended_assessment_setting: str
    mse202_concepts: List[str] = Field(min_length=1)
    mse302_concepts: List[str] = Field(min_length=1)
    concept_map_bridge: str
    materials_science_context: str
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
    metadata: QuestionMetadata
    body: str
    options: List[MCQOptionSchema] = Field(default_factory=list)
    model_answer: Optional[str] = None
    equations: List[EquationSchema] = Field(default_factory=list)
    quality_check: List[QualityCheckSchema] = Field(min_length=1)
    revision_options: List[str] = Field(min_length=2, max_length=3)


class AssessmentGenerationResponse(BaseModel):
    questions: List[QuestionResponse]


ASSESSMENT_PROVIDER_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["mcq", "short_answer", "long_answer"],
                    },
                    "body": {"type": "string"},
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "question_title": {"type": "string"},
                            "question_type": {
                                "type": "string",
                                "enum": ["mcq", "short_answer", "long_answer"],
                            },
                            "difficulty_level": {"type": "string"},
                            "intended_assessment_setting": {"type": "string"},
                            "mse202_concepts": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                            },
                            "mse302_concepts": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                            },
                            "concept_map_bridge": {"type": "string"},
                            "materials_science_context": {"type": "string"},
                        },
                        "required": [
                            "question_title",
                            "question_type",
                            "difficulty_level",
                            "intended_assessment_setting",
                            "mse202_concepts",
                            "mse302_concepts",
                            "concept_map_bridge",
                            "materials_science_context",
                        ],
                    },
                    "model_answer": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "body": {"type": "string"},
                                "is_correct": {"type": "boolean"},
                            },
                            "required": ["body", "is_correct"],
                        },
                    },
                    "quality_check": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "criterion": {"type": "string"},
                                "rating": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 5,
                                },
                                "comment": {"type": "string"},
                            },
                            "required": ["criterion", "rating", "comment"],
                        },
                        "minItems": 1,
                    },
                    "revision_options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 3,
                    },
                },
                "required": [
                    "type",
                    "body",
                    "metadata",
                    "quality_check",
                    "revision_options",
                ],
            },
        }
    },
    "required": ["questions"],
}
