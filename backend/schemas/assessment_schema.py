import re
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


_EQUATION_REFERENCE_PATTERN = re.compile(r"\[\[EQ:([A-Za-z0-9_-]+)\]\]")
_PLAIN_EQUATION_PATTERNS = (
    re.compile(r"\S\s*=\s*\S"),
    re.compile(r"(?<=[^\W_])[_^](?=[+\-−]?[^\W_])"),
    re.compile(r"\bsqrt\s*\(", re.IGNORECASE),
    re.compile(r"\$\$|\\\(|\\\[|\$[^$\r\n]+\$"),
)


def _equation_references(text: Optional[str]) -> List[str]:
    return _EQUATION_REFERENCE_PATTERN.findall(text or "")


def _plain_equation_excerpts(text: Optional[str]) -> List[str]:
    without_references = _EQUATION_REFERENCE_PATTERN.sub(
        lambda match: " " * len(match.group(0)),
        text or "",
    )
    excerpts = []
    for segment in re.split(r"(?<=[.!?])\s+|[\r\n]+", without_references):
        normalized = " ".join(segment.split())
        if not normalized:
            continue
        if any(pattern.search(normalized) for pattern in _PLAIN_EQUATION_PATTERNS):
            excerpts.append(normalized)
    return excerpts


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

    @model_validator(mode="after")
    def validate_flat_equation_references(self):
        has_structured_content = (
            self.body_segments is not None
            or self.model_answer_segments is not None
            or any(option.segments is not None for option in self.options)
        )
        if has_structured_content:
            return self

        labels = [equation.label for equation in self.equations]
        if len(labels) != len(set(labels)):
            raise ValueError("equation labels must be unique")

        equation_by_label = {
            equation.label: equation for equation in self.equations
        }
        question_content = [("body", self.body)] + [
            (f"options[{index}].body", option.body)
            for index, option in enumerate(self.options)
        ]
        solution_content = [("model_answer", self.model_answer)]
        question_references = [
            label
            for _, text in question_content
            for label in _equation_references(text)
        ]
        solution_references = [
            label
            for _, text in solution_content
            for label in _equation_references(text)
        ]
        all_references = question_references + solution_references

        for label in all_references:
            if label not in equation_by_label:
                raise ValueError(f"unknown equation label: {label}")

        shared_labels = sorted(
            set(question_references) & set(solution_references)
        )
        if shared_labels:
            raise ValueError(
                "equation labels referenced from both question and solution: "
                + ", ".join(shared_labels)
            )

        for label in question_references:
            if equation_by_label[label].location != "question":
                raise ValueError(
                    f"solution equation referenced from question: {label}"
                )
        for label in solution_references:
            if equation_by_label[label].location != "solution":
                raise ValueError(
                    f"question equation referenced from solution: {label}"
                )

        referenced_labels = set(all_references)
        for label in labels:
            if label not in referenced_labels:
                raise ValueError(f"equation is not referenced: {label}")

        plain_equation_errors = []
        for field_name, text in question_content + solution_content:
            excerpts = _plain_equation_excerpts(text)
            if not excerpts:
                continue
            offending_text = "; ".join(
                f'"{excerpt}"' for excerpt in excerpts
            )
            plain_equation_errors.append(
                f"{field_name}: mathematical expression must use an equation "
                f"reference; offending text: {offending_text}"
            )
        if plain_equation_errors:
            raise ValueError(" | ".join(plain_equation_errors))

        return self


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
                    "equations",
                    "revision_options",
                ],
            },
        }
    },
    "required": ["questions"],
}
