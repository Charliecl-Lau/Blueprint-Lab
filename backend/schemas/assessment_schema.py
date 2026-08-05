import re
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


_EQUATION_REFERENCE_PATTERN = re.compile(r"\[\[EQ:([A-Za-z0-9_-]+)\]\]")
_EQUATION_REFERENCE_TEXT = r"\[\[EQ:[A-Za-z0-9_-]+\]\]"
_FRAGMENTED_EQUATION_REFERENCE_PATTERN = re.compile(
    rf"(?:{_EQUATION_REFERENCE_TEXT}\s*[=+*/^−]|[=+*/^−]\s*"
    rf"{_EQUATION_REFERENCE_TEXT})"
)
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


def _fragmented_equation_reference_excerpts(
    text: Optional[str],
) -> List[str]:
    excerpts = []
    for segment in re.split(r"(?<=[.!?])\s+|[\r\n]+", text or ""):
        normalized = " ".join(segment.split())
        if _FRAGMENTED_EQUATION_REFERENCE_PATTERN.search(normalized):
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
    model_config = {"extra": "forbid"}

    body: str
    is_correct: bool
    segments: Optional[List[ContentSegment]] = None


class QuestionMetadata(BaseModel):
    model_config = {"extra": "forbid"}

    question_title: str
    question_type: Literal["mcq", "short_answer", "long_answer"]
    difficulty_level: str
    mse202_concepts: List[str] = Field(min_length=1)
    mse302_concepts: List[str] = Field(min_length=1)
    concept_map_bridge: Optional[str]
    materials_science_context: str
    estimated_time_minutes: int = Field(ge=1)
    learning_objectives: List[str] = Field(min_length=1)


class AssessmentMetadata(BaseModel):
    """Canonical document-level metadata, distinct from per-question metadata."""

    model_config = {"extra": "forbid"}

    prompt_template_id: Optional[str] = None
    actual_prompt_id: Optional[Union[str, int]] = None
    output_id: Optional[Union[str, int]] = None
    final_question_id: Optional[Union[str, int, List[Union[str, int]]]] = None
    question_title: str
    course: str
    topic: str
    question_type: str
    number_of_questions: int = Field(ge=1)
    difficulty_level: str
    cognitive_demand: str
    intended_assessment_setting: str
    mse202_concepts: List[str] = Field(min_length=1)
    mse302_concepts: List[str] = Field(min_length=1)
    concept_map_bridge: Optional[str]
    materials_science_context: str
    numerical_computation: str
    estimated_time: str
    learning_objectives: List[str] = Field(min_length=1)
    prompt_design_factors: List[str]
    additional_instructions: Optional[str] = None


class QualityCheckSchema(BaseModel):
    model_config = {"extra": "forbid"}

    criterion: str
    rating: int = Field(ge=1, le=5)
    comment: str


class EquationSchema(BaseModel):
    model_config = {"extra": "forbid"}

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
    model_config = {"protected_namespaces": (), "extra": "forbid"}

    type: Literal["mcq", "short_answer", "long_answer"]
    metadata: QuestionMetadata
    body: str
    body_segments: Optional[List[ContentSegment]] = None
    options: List[MCQOptionSchema] = Field(default_factory=list)
    model_answer: Optional[str] = None
    model_answer_segments: Optional[List[ContentSegment]] = None
    equations: List[EquationSchema]
    quality_checks: List[QualityCheckSchema] = Field(default_factory=list)
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

        duplicate_references = sorted(
            label for label in set(all_references) if all_references.count(label) > 1
        )
        if duplicate_references:
            raise ValueError(
                "equation labels must be referenced exactly once; repeated labels: "
                + ", ".join(duplicate_references)
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

        fragmented_reference_errors = []
        for field_name, text in question_content + solution_content:
            excerpts = _fragmented_equation_reference_excerpts(text)
            if not excerpts:
                continue
            offending_text = "; ".join(
                f'"{excerpt}"' for excerpt in excerpts
            )
            fragmented_reference_errors.append(
                f"{field_name}: fragmented equation references must be "
                "combined into one equation entry; operators cannot appear "
                "between or beside equation references; offending text: "
                f"{offending_text}"
            )
        if fragmented_reference_errors:
            raise ValueError(" | ".join(fragmented_reference_errors))

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
    model_config = {"extra": "forbid"}

    # Legacy saved assessments may predate the assessment-level contract. New
    # provider responses require it below, and persistence enriches legacy data
    # before a DOCX worker receives the canonical manifest.
    assessment_metadata: Optional[AssessmentMetadata] = None
    questions: List[QuestionResponse]

    @model_validator(mode="after")
    def validate_assessment_question_count(self):
        if (
            self.assessment_metadata is not None
            and self.assessment_metadata.number_of_questions != len(self.questions)
        ):
            raise ValueError(
                "assessment_metadata.number_of_questions must equal questions length"
            )
        return self


class ProviderMCQOptionSchema(BaseModel):
    model_config = {"extra": "forbid"}

    body: str
    is_correct: bool


class ProviderEquationSchema(BaseModel):
    model_config = {"extra": "forbid"}

    label: str
    expression: str = Field(min_length=1)
    location: Literal["question", "solution"]


class ProviderQuestionResponse(BaseModel):
    model_config = {"protected_namespaces": (), "extra": "forbid"}

    type: Literal["mcq", "short_answer", "long_answer"]
    metadata: QuestionMetadata
    body: str
    options: List[ProviderMCQOptionSchema] = Field(default_factory=list)
    model_answer: Optional[str] = None
    equations: List[ProviderEquationSchema]
    quality_checks: List[QualityCheckSchema] = Field(min_length=1)
    revision_options: List[str] = Field(min_length=2, max_length=3)


class ProviderAssessmentGenerationResponse(BaseModel):
    model_config = {"extra": "forbid"}

    assessment_metadata: AssessmentMetadata
    questions: List[ProviderQuestionResponse] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assessment_question_count(self):
        if self.assessment_metadata.number_of_questions != len(self.questions):
            raise ValueError(
                "assessment_metadata.number_of_questions must equal questions length"
            )
        return self


class AssessmentTraceability(BaseModel):
    model_config = {"extra": "forbid"}

    experiment_id: int
    condition_id: int
    run_id: int
    prompt_id: Optional[int]
    prompt_template_version: str
    assessment_id: int
    assessment_version: int = Field(ge=1)
    assessment_schema_version: str


class QuestionTraceability(BaseModel):
    model_config = {"extra": "forbid"}

    assessment_question_id: int
    ordinal: int = Field(ge=0)
    assessment_version: int = Field(ge=1)


class StoredQuestionResponse(QuestionResponse):
    traceability: QuestionTraceability


class StoredAssessmentPayload(BaseModel):
    model_config = {"extra": "forbid"}

    traceability: AssessmentTraceability
    assessment_metadata: AssessmentMetadata
    questions: List[StoredQuestionResponse]


ASSESSMENT_PROVIDER_SCHEMA = (
    ProviderAssessmentGenerationResponse.model_json_schema()
)
