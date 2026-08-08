from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal

from pydantic import ValidationError

from backend.schemas.assessment_schema import (
    AssessmentGenerationResponse,
    ProviderAssessmentGenerationResponse,
    ProviderContentSegment,
    ProviderQuestionResponse,
    QuestionResponse,
    _plain_equation_excerpts,
)
from backend.services.omml import parse_linear_expression


@dataclass(frozen=True)
class AssessmentIssue:
    code: str
    question_ordinal: int | None
    field_path: str
    message: str
    excerpt: str | None = None
    repair_scope: Literal["question", "assessment"] = "question"

    def as_dict(self) -> dict[str, Any]:
        target_section = None
        if ".model_answer_segments." in self.field_path:
            target_section = "solution"
        elif self.question_ordinal is not None:
            target_section = "question"
        return {
            "code": self.code,
            "error_type": "structural_validation_error",
            "question_ordinal": self.question_ordinal,
            "field_path": self.field_path,
            "target_path": self.field_path,
            "target_section": target_section,
            "question_id": None,
            "solution_id": None,
            "equation_id": None,
            "message": self.message,
            "excerpt": self.excerpt,
            "repair_scope": self.repair_scope,
            "expected_structure": (
                {"type": "math", "expression": "string", "display": "boolean"}
                if self.code == "raw_math_in_text_segment"
                else None
            ),
            "observed_structure": (
                {"type": "text", "excerpt": self.excerpt}
                if self.code == "raw_math_in_text_segment"
                else None
            ),
        }


class AssessmentCompilationError(ValueError):
    def __init__(
        self,
        issues: Iterable[AssessmentIssue],
        provider: ProviderAssessmentGenerationResponse,
    ) -> None:
        self.issues = tuple(issues)
        self.provider = provider
        summary = "; ".join(
            f"{issue.field_path}: {issue.message}" for issue in self.issues
        )
        super().__init__(summary)


def audit_provider_question(
    provider: ProviderQuestionResponse,
    question_ordinal: int,
) -> list[AssessmentIssue]:
    fields: list[tuple[str, list[ProviderContentSegment]]] = [
        ("body_segments", provider.body_segments),
        ("model_answer_segments", provider.model_answer_segments or []),
    ]
    fields.extend(
        (f"options.{ordinal}.segments", option.segments)
        for ordinal, option in enumerate(provider.options)
    )
    issues: list[AssessmentIssue] = []
    for field_path, segments in fields:
        for segment_ordinal, segment in enumerate(segments):
            if segment.type != "text":
                continue
            for excerpt in _plain_equation_excerpts(segment.text):
                issues.append(
                    AssessmentIssue(
                        code="raw_math_in_text_segment",
                        question_ordinal=question_ordinal,
                        field_path=(
                            f"questions.{question_ordinal}.{field_path}."
                            f"{segment_ordinal}.text"
                        ),
                        message=(
                            "Mathematical syntax must be represented by a math segment."
                        ),
                        excerpt=excerpt[:240],
                    )
                )
    return issues


def _label(
    question_ordinal: int,
    location: Literal["question", "solution"],
    field: str,
    math_ordinal: int,
) -> str:
    safe_field = "".join(
        character if character.isalnum() else "_" for character in field.lower()
    ).strip("_")
    return (
        f"q{question_ordinal + 1}_{location}_{safe_field}_m{math_ordinal + 1}"
    )


def _compile_segments(
    segments: list[ProviderContentSegment],
    *,
    question_ordinal: int,
    field: str,
    location: Literal["question", "solution"],
) -> tuple[str, list[dict[str, Any]]]:
    output: list[str] = []
    equations: list[dict[str, Any]] = []
    math_ordinal = 0
    for segment in segments:
        if segment.type == "text":
            output.append(segment.text)
            continue
        label = _label(question_ordinal, location, field, math_ordinal)
        output.append(f"[[EQ:{label}]]")
        equations.append(
            {
                "label": label,
                "expression": segment.expression,
                "math": parse_linear_expression(segment.expression),
                "location": location,
            }
        )
        math_ordinal += 1
    return "".join(output), equations


def compile_provider_question(
    provider: ProviderQuestionResponse,
    question_ordinal: int,
) -> QuestionResponse:
    body, equations = _compile_segments(
        provider.body_segments,
        question_ordinal=question_ordinal,
        field="body",
        location="question",
    )
    options: list[dict[str, Any]] = []
    for option_ordinal, option in enumerate(provider.options):
        option_body, option_equations = _compile_segments(
            option.segments,
            question_ordinal=question_ordinal,
            field=f"option_{option_ordinal + 1}",
            location="question",
        )
        options.append({"body": option_body, "is_correct": option.is_correct})
        equations.extend(option_equations)

    answer, answer_equations = _compile_segments(
        provider.model_answer_segments or [],
        question_ordinal=question_ordinal,
        field="model_answer",
        location="solution",
    )
    equations.extend(answer_equations)
    return QuestionResponse.model_validate(
        {
            "type": provider.type,
            "metadata": provider.metadata.model_dump(),
            "body": body,
            "options": options,
            "model_answer": answer,
            "equations": equations,
            "quality_checks": [item.model_dump() for item in provider.quality_checks],
            "revision_options": provider.revision_options,
        }
    )


def _issues_from_validation(
    error: ValidationError,
    question_ordinal: int,
) -> list[AssessmentIssue]:
    issues: list[AssessmentIssue] = []
    for item in error.errors():
        local_path = ".".join(str(value) for value in item.get("loc", ()))
        field_path = f"questions.{question_ordinal}"
        if local_path:
            field_path += f".{local_path}"
        issues.append(
            AssessmentIssue(
                code=str(item.get("type", "validation_error")),
                question_ordinal=question_ordinal,
                field_path=field_path,
                message=str(item.get("msg", "Question validation failed")),
            )
        )
    return issues


def compile_provider_assessment(
    provider: ProviderAssessmentGenerationResponse,
    *,
    expected_questions: int | None = None,
) -> AssessmentGenerationResponse:
    issues: list[AssessmentIssue] = []
    compiled: list[QuestionResponse | None] = []
    if expected_questions is not None and len(provider.questions) != expected_questions:
        issues.append(
            AssessmentIssue(
                code="question_count_mismatch",
                question_ordinal=None,
                field_path="questions",
                message=(
                    f"expected {expected_questions} questions, "
                    f"received {len(provider.questions)}"
                ),
                repair_scope="assessment",
            )
        )
    for ordinal, question in enumerate(provider.questions):
        question_audit = audit_provider_question(question, ordinal)
        if question_audit:
            compiled.append(None)
            issues.extend(question_audit)
            continue
        try:
            compiled.append(compile_provider_question(question, ordinal))
        except ValidationError as exc:
            compiled.append(None)
            issues.extend(_issues_from_validation(exc, ordinal))
    if issues:
        raise AssessmentCompilationError(issues, provider)
    return AssessmentGenerationResponse.model_validate(
        {
            "assessment_metadata": provider.assessment_metadata.model_dump(),
            "questions": [item.model_dump() for item in compiled if item is not None],
        }
    )
