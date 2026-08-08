from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

from backend.schemas.assessment_schema import (
    ProviderAssessmentGenerationResponse,
    ProviderQuestionResponse,
    ProviderSegmentReplacement,
)
from backend.services.reproducibility import sha256_text


class LocalizedRepairRejected(ValueError):
    """Raised when a replacement is invalid or changes substantive content."""


@dataclass(frozen=True)
class SegmentRepairTarget:
    path: str
    tokens: tuple[str | int, ...]
    question_ordinal: int
    section: str
    content: dict[str, Any]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: Any) -> str:
    return sha256_text(canonical_json(value))


def segment_target(
    provider: ProviderAssessmentGenerationResponse,
    field_path: str,
) -> SegmentRepairTarget | None:
    parts = field_path.split(".")
    if len(parts) < 5 or parts[0] != "questions" or not parts[1].isdigit():
        return None
    if parts[-1] == "text":
        parts = parts[:-1]
    tokens: list[str | int] = [int(part) if part.isdigit() else part for part in parts]
    if not any(part in {"body_segments", "model_answer_segments", "segments"} for part in parts):
        return None
    payload: Any = provider.model_dump(mode="json")
    try:
        for token in tokens:
            payload = payload[token]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("type") not in {"text", "math"}:
        return None
    section = "solution" if "model_answer_segments" in parts else "question"
    return SegmentRepairTarget(
        path=".".join(parts),
        tokens=tuple(tokens),
        question_ordinal=int(parts[1]),
        section=section,
        content=copy.deepcopy(payload),
    )


def _projection(segments: list[dict[str, Any]]) -> str:
    output: list[str] = []
    for segment in segments:
        if segment.get("type") == "text":
            output.append(str(segment.get("text", "")))
        elif segment.get("type") == "math":
            output.append(str(segment.get("expression", "")))
        else:
            raise LocalizedRepairRejected("replacement contains an unknown segment type")
    return "".join(output)


def apply_segment_replacement(
    provider: ProviderAssessmentGenerationResponse,
    target: SegmentRepairTarget,
    replacement: ProviderSegmentReplacement,
) -> ProviderAssessmentGenerationResponse:
    replacement_payload = [item.model_dump(mode="json") for item in replacement.segments]
    if _projection(replacement_payload) != _projection([target.content]):
        raise LocalizedRepairRejected(
            "replacement changes wording, notation, or numerical content"
        )

    patched = provider.model_dump(mode="json")
    parent: Any = patched
    for token in target.tokens[:-1]:
        parent = parent[token]
    index = target.tokens[-1]
    if not isinstance(parent, list) or not isinstance(index, int):
        raise LocalizedRepairRejected("target is not a replaceable content segment")
    parent[index : index + 1] = replacement_payload
    return ProviderAssessmentGenerationResponse.model_validate(patched)


def extract_segment_replacement_from_question(
    provider: ProviderAssessmentGenerationResponse,
    target: SegmentRepairTarget,
    candidate: ProviderQuestionResponse,
) -> ProviderSegmentReplacement:
    """Compatibility adapter that rejects every candidate change outside the target."""

    ordinal = target.question_ordinal
    before_question = provider.questions[ordinal].model_dump(mode="json")
    after_question = candidate.model_dump(mode="json")
    local_tokens = target.tokens[2:]
    before_parent: Any = before_question
    after_parent: Any = after_question
    for token in local_tokens[:-1]:
        before_parent = before_parent[token]
        after_parent = after_parent[token]
    index = local_tokens[-1]
    if not isinstance(before_parent, list) or not isinstance(after_parent, list):
        raise LocalizedRepairRejected("question response did not address a segment list")
    suffix_count = len(before_parent) - int(index) - 1
    prefix = before_parent[: int(index)]
    suffix = before_parent[int(index) + 1 :]
    if after_parent[: int(index)] != prefix:
        raise LocalizedRepairRejected("question response changed content before the target")
    if suffix_count and after_parent[-suffix_count:] != suffix:
        raise LocalizedRepairRejected("question response changed content after the target")
    stop = len(after_parent) - suffix_count if suffix_count else len(after_parent)
    replacement_items = after_parent[int(index) : stop]
    normalized_before = copy.deepcopy(before_question)
    normalized_after = copy.deepcopy(after_question)
    left: Any = normalized_before
    right: Any = normalized_after
    for token in local_tokens[:-1]:
        left = left[token]
        right = right[token]
    left[:] = right[:]
    if normalized_before != normalized_after:
        raise LocalizedRepairRejected("question response attempted an unrelated mutation")
    return ProviderSegmentReplacement.model_validate({"segments": replacement_items})


def non_target_content_unchanged(
    before: ProviderAssessmentGenerationResponse,
    after: ProviderAssessmentGenerationResponse,
    target: SegmentRepairTarget,
) -> bool:
    expected = before.model_dump(mode="json")
    actual = after.model_dump(mode="json")
    expected_parent: Any = expected
    actual_parent: Any = actual
    for token in target.tokens[:-1]:
        expected_parent = expected_parent[token]
        actual_parent = actual_parent[token]
    index = target.tokens[-1]
    expected_parent[index : index + 1] = actual_parent[index : index + 1]
    return expected == actual
