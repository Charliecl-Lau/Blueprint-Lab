from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


class TextMathNode(BaseModel):
    type: Literal["text"]
    text: str


class SymbolMathNode(BaseModel):
    type: Literal["symbol"]
    name: str


class NumberMathNode(BaseModel):
    type: Literal["number"]
    value: str


class OperatorMathNode(BaseModel):
    type: Literal["operator"]
    value: str


class SequenceMathNode(BaseModel):
    type: Literal["sequence"]
    items: List["MathNode"] = Field(min_length=1)


class EquationMathNode(BaseModel):
    type: Literal["equation"]
    left: "MathNode"
    right: "MathNode"


class FractionMathNode(BaseModel):
    type: Literal["fraction"]
    numerator: "MathNode"
    denominator: "MathNode"


class DifferentialMathNode(BaseModel):
    type: Literal["differential"]
    variable: str


class ProductMathNode(BaseModel):
    type: Literal["product"]
    terms: List["MathNode"] = Field(min_length=2)
    operator: Literal["implicit", "dot", "cross"] = "implicit"


class SubscriptMathNode(BaseModel):
    type: Literal["subscript"]
    base: "MathNode"
    subscript: "MathNode"


class SuperscriptMathNode(BaseModel):
    type: Literal["superscript"]
    base: "MathNode"
    superscript: "MathNode"


class RadicalMathNode(BaseModel):
    type: Literal["radical"]
    radicand: "MathNode"
    degree: Optional["MathNode"] = None


class MatrixMathNode(BaseModel):
    type: Literal["matrix"]
    rows: List[List["MathNode"]] = Field(min_length=1)


MathNode = Annotated[
    Union[
        TextMathNode,
        SymbolMathNode,
        NumberMathNode,
        OperatorMathNode,
        SequenceMathNode,
        EquationMathNode,
        FractionMathNode,
        DifferentialMathNode,
        ProductMathNode,
        SubscriptMathNode,
        SuperscriptMathNode,
        RadicalMathNode,
        MatrixMathNode,
    ],
    Field(discriminator="type"),
]


for _recursive_model in (
    SequenceMathNode,
    EquationMathNode,
    FractionMathNode,
    ProductMathNode,
    SubscriptMathNode,
    SuperscriptMathNode,
    RadicalMathNode,
    MatrixMathNode,
):
    _recursive_model.model_rebuild()


class TextSegment(BaseModel):
    type: Literal["text"]
    text: str


class MathSegment(BaseModel):
    type: Literal["math"]
    math: MathNode


ContentSegment = Annotated[
    Union[TextSegment, MathSegment],
    Field(discriminator="type"),
]


class MCQOptionSchema(BaseModel):
    body: str
    is_correct: bool
    segments: Optional[List[ContentSegment]] = None


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
    math: Optional[MathNode] = None
    expression: Optional[str] = None
    location: Literal["question", "solution"]

    @model_validator(mode="after")
    def require_math_or_legacy_expression(self):
        if self.math is None and not self.expression:
            raise ValueError("equation requires structured math")
        return self


class QuestionResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    type: Literal["mcq", "short_answer", "long_answer"]
    metadata: QuestionMetadata
    body: str
    body_segments: Optional[List[ContentSegment]] = None
    options: List[MCQOptionSchema] = Field(default_factory=list)
    model_answer: Optional[str] = None
    model_answer_segments: Optional[List[ContentSegment]] = None
    equations: List[EquationSchema] = Field(default_factory=list)
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
                    "equations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "expression": {"type": "string"},
                                "location": {
                                    "type": "string",
                                    "enum": ["question", "solution"],
                                },
                            },
                            "required": ["label", "expression", "location"],
                        },
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
                    "revision_options",
                ],
            },
        }
    },
    "required": ["questions"],
}
