from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


SourceRole = Literal["course_syllabus", "bridge_map", "few_shot_example", "rubric", "reference_content", "instructor_example"]


class SourceBinding(BaseModel):
    source_document_id: int
    role: SourceRole
    ordinal: int = Field(ge=0)
    model_config = {"extra": "forbid"}


class ModelSettings(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    version: Optional[str] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    seed: Optional[int] = None
    max_tokens: Optional[int] = None


class RunCreate(BaseModel):
    source_bindings: list[SourceBinding] = Field(default_factory=list)
    model_settings: Optional[ModelSettings] = None
    model_config = {"protected_namespaces": ()}


class RunSummary(BaseModel):
    id: int
    condition_id: int
    run_number: int
    status: Literal[
        "pending",
        "prompting",
        "generating",
        "documenting",
        "complete",
        "error",
    ]
    model_settings: dict
    reference_pdf_filenames: list[str] = Field(default_factory=list)
    model_config = {"from_attributes": True, "protected_namespaces": ()}


RecordingState = Literal["not_recorded", "in_progress", "recorded"]


class StageUsage(BaseModel):
    stage: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int]
    model_calls: int
    cached_content_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    extra_token_counts: Optional[dict[str, int]] = None
    model_config = {"protected_namespaces": ()}


class TokenTotals(BaseModel):
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int]
    model_calls: Optional[int]
    recording_state: RecordingState
    stages: list[StageUsage] = Field(default_factory=list)
    model_config = {"protected_namespaces": ()}


class RunDetail(BaseModel):
    id: int
    run_id: int
    experiment_id: int
    condition_id: int
    run_number: int
    status: str
    viewer_ready_at: Optional[datetime] = None
    progress_message: Optional[str] = None
    evaluation_status: Literal["not_started", "in_progress", "complete", "failed"]
    grading_available: bool
    grading_question_id: Optional[int] = None
    model_settings: dict
    token_usage: TokenTotals
    prompt: Optional[dict] = None
    assessment: Optional[dict] = None
    sources: list[dict] = Field(default_factory=list)
    error: Optional[dict] = None
    artifact_available: bool
    reference_pdf_filenames: list[str] = Field(default_factory=list)
    model_config = {"protected_namespaces": ()}


class RecentRun(BaseModel):
    id: int
    experiment_id: int
    condition_id: int
    run_number: int
    status: str
    topic: str
    condition_label: str
    created_at: datetime
    completed_at: Optional[datetime]
    token_usage: TokenTotals
    reference_pdf_filenames: list[str] = Field(default_factory=list)


def _reported_sum(items, attribute: str) -> Optional[int]:
    values = [getattr(item, attribute) for item in items]
    reported = [value for value in values if value is not None]
    return sum(reported) if reported else None


def token_usage_detail(run) -> dict:
    aggregates = (
        run.input_tokens,
        run.output_tokens,
        run.total_tokens,
        run.model_call_count,
    )
    if all(value is None for value in aggregates):
        recording_state: RecordingState = "not_recorded"
    elif run.status in {"complete", "error"}:
        recording_state = "recorded"
    else:
        recording_state = "in_progress"

    grouped: dict[str, list] = {}
    for call in sorted(run.model_call_usages, key=lambda item: (item.id or 0)):
        grouped.setdefault(call.stage, []).append(call)

    stages = []
    for stage, calls in grouped.items():
        stage_usage = {
            "stage": stage,
            "input_tokens": _reported_sum(calls, "input_tokens"),
            "output_tokens": _reported_sum(calls, "output_tokens"),
            "total_tokens": _reported_sum(calls, "total_tokens"),
            "model_calls": len(calls),
        }
        cached = _reported_sum(calls, "cached_content_tokens")
        reasoning = _reported_sum(calls, "reasoning_tokens")
        if cached is not None:
            stage_usage["cached_content_tokens"] = cached
        if reasoning is not None:
            stage_usage["reasoning_tokens"] = reasoning
        extras: dict[str, int] = {}
        for call in calls:
            for key, value in (call.extra_token_counts or {}).items():
                extras[key] = extras.get(key, 0) + value
        if extras:
            stage_usage["extra_token_counts"] = extras
        stages.append(stage_usage)

    return {
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "total_tokens": run.total_tokens,
        "model_calls": run.model_call_count,
        "recording_state": recording_state,
        "stages": stages,
    }
