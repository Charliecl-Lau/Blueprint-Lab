"""Safe recovery for structurally renderable assessment responses.

This module intentionally repairs only explicit component-indexed identifiers.
It never guesses what a bare mathematical variable means.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any
import re

from pydantic import ValidationError

from backend.schemas.assessment_schema import AssessmentGenerationResponse


_REFERENCE_PATTERN = re.compile(r"\[\[EQ:[A-Za-z0-9_-]+\]\]")
_COMPONENT_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?P<base>[A-Za-z]+)_(?P<component>[A-Za-z])(?![A-Za-z0-9_])"
)


@dataclass(frozen=True)
class RecoveryResult:
    parsed_json: dict[str, Any] | None
    actions: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    strictly_valid: bool
    structurally_renderable: bool


def _validation_issues(error: ValidationError) -> list[dict[str, Any]]:
    issues = []
    for item in error.errors():
        location = list(item.get("loc", ()))
        question_ordinal = next(
            (
                following
                for current, following in zip(location, location[1:])
                if current == "questions" and isinstance(following, int)
            ),
            None,
        )
        issues.append(
            {
                "code": "validation_error",
                "question_ordinal": question_ordinal,
                "field_path": ".".join(str(value) for value in location),
                "excerpt": None,
                "message": item["msg"],
                "recoverable": False,
            }
        )
    return issues


def _is_structurally_renderable(payload: Any, expected_questions: int | None) -> bool:
    if not isinstance(payload, dict):
        return False
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        return False
    if expected_questions is not None and len(questions) != expected_questions:
        return False
    return all(
        isinstance(question, dict)
        and isinstance(question.get("body"), str)
        and question.get("type") in {"mcq", "short_answer", "long_answer"}
        for question in questions
    )


def _field_entries(question: dict[str, Any]) -> list[tuple[str, str, str]]:
    fields: list[tuple[str, str, str]] = []
    if isinstance(question.get("body"), str):
        fields.append(("body", "question", question["body"]))
    for index, option in enumerate(question.get("options") or []):
        if isinstance(option, dict) and isinstance(option.get("body"), str):
            fields.append((f"options[{index}].body", "question", option["body"]))
    if isinstance(question.get("model_answer"), str):
        fields.append(("model_answer", "solution", question["model_answer"]))
    return fields


def _set_field(question: dict[str, Any], field_path: str, value: str) -> None:
    if field_path == "body":
        question["body"] = value
    elif field_path == "model_answer":
        question["model_answer"] = value
    else:
        index = int(field_path.removeprefix("options[").split("]", 1)[0])
        question["options"][index]["body"] = value


def _reference_spans(value: str) -> list[tuple[int, int]]:
    return [match.span() for match in _REFERENCE_PATTERN.finditer(value)]


def _inside_span(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def _canonical_component_token(match: re.Match[str]) -> str:
    return f"{match.group('base')}_{match.group('component').lower()}"


def _find_matching_label(
    equations: list[dict[str, Any]], expression: str, location: str
) -> str | None:
    for equation in equations:
        if (
            equation.get("location") == location
            and equation.get("expression") == expression
            and isinstance(equation.get("label"), str)
        ):
            return equation["label"]
    return None


def _new_label(
    equations: list[dict[str, Any]], question_ordinal: int, field_path: str, expression: str
) -> str:
    used = {str(item.get("label")) for item in equations}
    field = re.sub(r"[^a-z0-9]+", "_", field_path.lower()).strip("_")
    symbol = re.sub(r"[^a-z0-9]+", "_", expression.lower()).strip("_")
    prefix = f"auto_q{question_ordinal + 1}_{field}_{symbol}"
    suffix = 1
    label = f"{prefix}_{suffix}"
    while label in used:
        suffix += 1
        label = f"{prefix}_{suffix}"
    return label


def _recover_component_symbols(payload: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for ordinal, question in enumerate(payload.get("questions", [])):
        if not isinstance(question, dict):
            continue
        equations = question.setdefault("equations", [])
        if not isinstance(equations, list):
            continue
        for field_path, location, value in _field_entries(question):
            spans = _reference_spans(value)
            replacements: list[tuple[int, int, str, str, str]] = []
            for match in _COMPONENT_TOKEN_PATTERN.finditer(value):
                if _inside_span(match.start(), spans):
                    continue
                original = match.group(0)
                canonical = _canonical_component_token(match)
                label = _find_matching_label(equations, canonical, location)
                if label is None:
                    label = _new_label(equations, ordinal, field_path, canonical)
                    equations.append(
                        {
                            "label": label,
                            "expression": canonical,
                            "location": location,
                        }
                    )
                replacements.append(
                    (match.start(), match.end(), original, canonical, label)
                )
            if not replacements:
                continue
            transformed = value
            for start, end, original, canonical, label in reversed(replacements):
                transformed = transformed[:start] + f"[[EQ:{label}]]" + transformed[end:]
                actions.append(
                    {
                        "type": "component_symbol_reference",
                        "question_ordinal": ordinal,
                        "field_path": field_path,
                        "original": original,
                        "canonical": canonical,
                        "label": label,
                        "location": location,
                    }
                )
            _set_field(question, field_path, transformed)
    return sorted(
        actions,
        key=lambda item: (item["question_ordinal"], item["field_path"], item["label"]),
    )


def recover_assessment_payload(
    payload: Any, *, expected_questions: int | None = None
) -> RecoveryResult:
    """Return a strictly valid or safely viewable assessment candidate."""

    if not _is_structurally_renderable(payload, expected_questions):
        return RecoveryResult(
            parsed_json=None,
            actions=[],
            issues=[
                {
                    "code": "unsafe_assessment_structure",
                    "question_ordinal": None,
                    "field_path": "questions",
                    "excerpt": None,
                    "message": "Assessment response cannot be rendered safely.",
                    "recoverable": False,
                }
            ],
            strictly_valid=False,
            structurally_renderable=False,
        )

    candidate = deepcopy(payload)
    try:
        valid = AssessmentGenerationResponse.model_validate(candidate)
        return RecoveryResult(
            parsed_json=valid.model_dump(),
            actions=[],
            issues=[],
            strictly_valid=True,
            structurally_renderable=True,
        )
    except ValidationError:
        pass

    actions = _recover_component_symbols(candidate)
    try:
        valid = AssessmentGenerationResponse.model_validate(candidate)
        return RecoveryResult(
            parsed_json=valid.model_dump(),
            actions=actions,
            issues=[],
            strictly_valid=True,
            structurally_renderable=True,
        )
    except ValidationError as exc:
        return RecoveryResult(
            parsed_json=candidate,
            actions=actions,
            issues=_validation_issues(exc),
            strictly_valid=False,
            structurally_renderable=True,
        )
