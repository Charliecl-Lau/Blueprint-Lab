"""Persistence and lifecycle helpers for recovered assessments."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.models import Assessment, Run
from backend.models.experiment import utc_now
from backend.services.assessment_evaluation import persist_assessment_questions
from backend.services.assessment_recovery import RecoveryResult, recover_assessment_payload
from backend.services.assessment_traceability import enrich_assessment_traceability
from backend.services.llm_client import _parse_json
from backend.services.reproducibility import canonical_json, sha256_text


RECOVERY_IMPLEMENTATION_VERSION = "2026-07-27.1"
RecoveryState = Literal["valid", "warning", "invalid"]


class AssessmentRecoveryError(RuntimeError):
    status_code = 409


def assessment_is_accepted_or_valid(run: Run) -> bool:
    assessment = run.assessment
    return bool(
        assessment
        and (
            run.status == "complete"
            or (
                run.status == "complete_with_warnings"
                and assessment.defects_accepted_at is not None
            )
        )
    )


def _set_candidate(
    assessment: Assessment,
    result: RecoveryResult,
    *,
    source: str,
) -> None:
    assessment.parsed_json = result.parsed_json
    assessment.parsed_json_hash = (
        sha256_text(canonical_json(result.parsed_json))
        if result.parsed_json is not None
        else None
    )
    assessment.validation_issues = list(result.issues)
    actions = list(result.actions)
    actions.append(
        {
            "type": "recovery_processed",
            "source": source,
            "version": RECOVERY_IMPLEMENTATION_VERSION,
            "at": utc_now().isoformat(),
        }
    )
    assessment.recovery_actions = actions
    assessment.validation_status = "valid" if result.strictly_valid else (
        "warning" if result.structurally_renderable else "invalid"
    )


def mark_strictly_valid(
    assessment: Assessment, parsed_json: dict, *, recovery_actions: list[dict] | None = None
) -> None:
    assessment.parsed_json = parsed_json
    assessment.parsed_json_hash = sha256_text(canonical_json(parsed_json))
    assessment.validation_status = "valid"
    assessment.validation_issues = []
    assessment.recovery_actions = list(recovery_actions or [])


def recover_saved_assessment(
    db: Session, run: Run, *, source: str
) -> RecoveryState:
    """Parse and safely recover the saved raw response without a provider call."""

    assessment = run.assessment
    if assessment is None:
        raise AssessmentRecoveryError("Run has no saved assessment response")
    try:
        payload = _parse_json(assessment.raw_response_text)
    except ValueError as exc:
        result = RecoveryResult(
            parsed_json=None,
            actions=[],
            issues=[
                {
                    "code": "invalid_json",
                    "question_ordinal": None,
                    "field_path": "",
                    "excerpt": None,
                    "message": str(exc),
                    "recoverable": False,
                }
            ],
            strictly_valid=False,
            structurally_renderable=False,
        )
    else:
        result = recover_assessment_payload(
            payload,
            expected_questions=run.experiment.number_of_questions,
        )

    _set_candidate(assessment, result, source=source)
    if result.strictly_valid:
        persist_assessment_questions(db, assessment)
        enrich_assessment_traceability(db, assessment)
        return "valid"
    if result.structurally_renderable:
        persist_assessment_questions(db, assessment)
        return "warning"
    return "invalid"


def set_warning_run_state(run: Run) -> None:
    run.status = "complete_with_warnings"
    run.progress_message = "Completed with validation warnings"
    run.error_type = "assessment_validation_warning"
    issue_count = len(run.assessment.validation_issues) if run.assessment else 0
    run.error_message = (
        f"Assessment is viewable with {issue_count} unresolved validation warning(s)."
    )
    run.viewer_ready_at = run.viewer_ready_at or utc_now()
    run.completed_at = utc_now()


def accept_assessment_defects(
    db: Session, run: Run, reviewer_id: str
) -> Assessment:
    assessment = run.assessment
    if assessment is None or assessment.parsed_json is None:
        raise AssessmentRecoveryError("Assessment is unavailable for acceptance")
    if run.status != "complete_with_warnings" or assessment.validation_status != "warning":
        raise AssessmentRecoveryError("Assessment has no unresolved validation warnings")
    if assessment.defects_accepted_at is not None:
        return assessment
    assessment.defects_accepted_at = utc_now()
    assessment.defects_accepted_by = reviewer_id
    run.progress_message = "Completed with warnings (accepted)"
    return assessment
