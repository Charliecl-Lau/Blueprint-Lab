import re
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import Condition, Experiment, Run, RunReferencePdf
from backend.schemas.experiment_schema import ExperimentCreate
from backend.services.actual_prompt import build_condition_label


@dataclass(frozen=True)
class ValidationIssue:
    section: str
    field: str
    label: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


class ExperimentValidationError(ValueError):
    def __init__(self, issues: Iterable[ValidationIssue]):
        self.issues = list(issues)
        super().__init__("Experiment submission validation failed")


_ASSESSMENT_FIELDS = {
    "course": "Course name",
    "topic": "Topic",
    "learning_objectives": "Learning objectives",
    "assessment_type": "Assessment format",
    "difficulty": "Difficulty",
    "number_of_questions": "Number of questions",
    "estimated_time_minutes": "Estimated student completion time",
    "cognitive_demand": "Cognitive demand",
    "additional_instruction": "Additional instruction",
    "prompt_structure": "Prompt structure",
}
_FACTOR_LABELS = {
    "concept_bridge": "Concept Bridge: add bridge content",
    "few_shot": "Few-shot Examples: add example content",
    "reference_content": "Reference Content: add reference content",
    "reasoning_guidance": "Reasoning Guidance: add guidance content",
}


def _safe_message(error_type: str, label: str) -> str:
    if error_type in {"missing", "string_too_short"}:
        return f"{label} is required."
    if error_type in {"literal_error", "enum"}:
        return f"Select a supported {label.lower()}."
    if error_type in {
        "greater_than_equal",
        "less_than_equal",
        "int_parsing",
        "int_type",
    }:
        return f"Enter a valid value for {label.lower()}."
    return f"Check {label.lower()} and try again."


def validation_issues_from_request_errors(errors: list[dict]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for error in errors:
        location = [str(item) for item in error.get("loc", ()) if item != "body"]
        field = ".".join(location)
        leaf = location[-1] if location else ""
        context_error = str(error.get("ctx", {}).get("error", ""))
        enabled_factor = re.search(
            r"Enabled factor '([a-z_]+)' requires content", context_error
        )
        if enabled_factor:
            factor = enabled_factor.group(1)
            label = _FACTOR_LABELS[factor]
            issues.append(
                ValidationIssue(
                    section="Prompt Design Factors",
                    field=f"factor_inputs.{factor}",
                    label=label,
                    message=f"{label} is required when the factor is enabled.",
                )
            )
            continue
        if leaf in _ASSESSMENT_FIELDS:
            label = _ASSESSMENT_FIELDS[leaf]
            issues.append(
                ValidationIssue(
                    section="Assessment Details",
                    field=leaf,
                    label=label,
                    message=_safe_message(error.get("type", ""), label),
                )
            )
            continue
        if leaf in _FACTOR_LABELS:
            label = _FACTOR_LABELS[leaf]
            issues.append(
                ValidationIssue(
                    section="Prompt Design Factors",
                    field=field or f"factor_inputs.{leaf}",
                    label=label,
                    message=_safe_message(error.get("type", ""), label),
                )
            )
            continue
        if leaf == "idempotency-key":
            issues.append(
                ValidationIssue(
                    section="Submission",
                    field="idempotency_key",
                    label="Submission key",
                    message="A valid submission key is required.",
                )
            )
            continue
        issues.append(
            ValidationIssue(
                section="Submission",
                field=field or "request",
                label="Request",
                message="Check the submitted value and try again.",
            )
        )
    return issues


def _validated_idempotency_key(value: str) -> str:
    key = value.strip()
    if not key or len(key) > 64:
        raise ExperimentValidationError(
            [
                ValidationIssue(
                    section="Submission",
                    field="idempotency_key",
                    label="Submission key",
                    message="A nonblank submission key of at most 64 characters is required.",
                )
            ]
        )
    return key


def _existing_graph(db: Session, key: str):
    experiment = db.scalar(
        select(Experiment).where(Experiment.idempotency_key == key)
    )
    if experiment is None:
        return None
    return experiment, experiment.runs[0], False


def existing_experiment_graph(db: Session, idempotency_key: str):
    return _existing_graph(db, _validated_idempotency_key(idempotency_key))


def validate_reference_pdf_filenames(
    payload: ExperimentCreate,
    reference_pdf_filenames: Sequence[str],
) -> None:
    count = len(reference_pdf_filenames)
    enabled = payload.factors.reference_content
    if enabled and count == 0:
        message = "Upload at least one PDF when Reference Content is enabled."
    elif enabled and count > 3:
        message = "Upload no more than three PDFs for Reference Content."
    elif not enabled and count:
        message = "Enable Reference Content before uploading reference PDFs."
    else:
        return
    raise ExperimentValidationError(
        [
            ValidationIssue(
                section="Prompt Design Factors",
                field="reference_pdfs",
                label="Reference Content PDFs",
                message=message,
            )
        ]
    )


def create_experiment_with_run(
    db: Session,
    payload: ExperimentCreate,
    idempotency_key: str,
    reference_pdf_filenames: Sequence[str] = (),
):
    key = _validated_idempotency_key(idempotency_key)
    existing = _existing_graph(db, key)
    if existing is not None:
        return existing
    validate_reference_pdf_filenames(payload, reference_pdf_filenames)

    experiment = Experiment(
        idempotency_key=key,
        course=payload.course,
        topic=payload.topic,
        learning_objectives=payload.learning_objectives,
        assessment_type=payload.assessment_type,
        difficulty=payload.difficulty,
        number_of_questions=payload.number_of_questions,
        estimated_time_minutes=payload.estimated_time_minutes,
        cognitive_demand=payload.cognitive_demand,
        additional_instruction=payload.additional_instruction,
    )
    factor_inputs = payload.factor_inputs.model_dump(exclude_none=True)
    factor_inputs.pop("reference_content", None)
    condition = Condition(
        experiment=experiment,
        condition_code="C100",
        prompt_structure=payload.prompt_structure,
        concept_bridge_enabled=payload.factors.concept_bridge,
        few_shot_enabled=payload.factors.few_shot,
        reference_content_enabled=payload.factors.reference_content,
        reasoning_guidance_enabled=payload.factors.reasoning_guidance,
        factor_configuration=payload.factors.model_dump(),
        factor_inputs=factor_inputs,
        condition_label=build_condition_label(payload.factors),
    )
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="pending",
        model_settings={},
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        model_call_count=0,
    )
    run.reference_pdfs = [
        RunReferencePdf(ordinal=ordinal, original_filename=filename)
        for ordinal, filename in enumerate(reference_pdf_filenames)
    ]
    db.add(experiment)
    try:
        db.flush()
        db.commit()
        db.refresh(experiment)
        db.refresh(run)
        return experiment, run, True
    except IntegrityError:
        db.rollback()
        winner = _existing_graph(db, key)
        if winner is None:
            raise
        return winner
    except Exception:
        db.rollback()
        raise
