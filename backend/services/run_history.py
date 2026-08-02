from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.run import Run


TERMINAL_HISTORY_STATUSES = ("complete", "complete_with_warnings", "error")


class RunHistoryError(RuntimeError):
    status_code = 409


class RunHistoryNotFoundError(RunHistoryError):
    status_code = 404


def list_terminal_run_summaries(db: Session, limit: int) -> list[dict]:
    runs = db.scalars(
        select(Run)
        .where(Run.status.in_(TERMINAL_HISTORY_STATUSES))
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": run.id,
            "experiment_id": run.experiment_id,
            "condition_id": run.condition_id,
            "run_number": run.run_number,
            "status": run.status,
            "display_status": "failed" if run.status == "error" else "completed",
            "topic": run.experiment.topic,
            "display_at": (
                run.completed_at
                or run.viewer_ready_at
                or run.started_at
                or run.created_at
            ),
        }
        for run in runs
    ]


def get_run_history(db: Session, run_id: int) -> dict:
    run = db.get(Run, run_id)
    if run is None:
        raise RunHistoryNotFoundError("Run not found")
    if run.status not in TERMINAL_HISTORY_STATUSES:
        raise RunHistoryError("Run history is available only after the run finishes")

    experiment = run.experiment
    condition = run.condition
    base = {
        "id": run.id,
        "experiment_id": run.experiment_id,
        "condition_id": run.condition_id,
        "run_number": run.run_number,
        "status": run.status,
        "display_status": "failed" if run.status == "error" else "completed",
        "assessment_details": {
            "course": experiment.course,
            "topic": experiment.topic,
            "learning_objectives": list(experiment.learning_objectives),
            "assessment_type": experiment.assessment_type,
            "difficulty": experiment.difficulty,
            "number_of_questions": experiment.number_of_questions,
            "estimated_time_minutes": experiment.estimated_time_minutes,
            "cognitive_demand": experiment.cognitive_demand,
            "additional_instruction": experiment.additional_instruction,
            "prompt_structure": condition.prompt_structure,
            "factor_configuration": {
                "concept_bridge": condition.concept_bridge_enabled,
                "few_shot": condition.few_shot_enabled,
                "reference_content": condition.reference_content_enabled,
                "reasoning_guidance": condition.reasoning_guidance_enabled,
            },
            "factor_inputs": deepcopy(condition.factor_inputs),
            "reference_pdf_filenames": list(run.reference_pdf_filenames),
        },
        "actual_prompt": run.prompt.actual_prompt if run.prompt else None,
    }
    if run.status == "error":
        return {
            **base,
            "questions": None,
            "question_ids": None,
            "artifact": None,
            "evaluation_available": False,
        }

    assessment = run.assessment
    questions = (
        deepcopy(assessment.parsed_json.get("questions", []))
        if assessment and assessment.parsed_json else []
    )
    ordered = (
        sorted(assessment.questions, key=lambda item: (item.ordinal, item.id))
        if assessment else []
    )
    artifact = run.document_artifact
    return {
        **base,
        "questions": questions,
        "question_ids": [item.id for item in ordered],
        "artifact": (
            {"available": True, "filename": artifact.filename}
            if artifact else None
        ),
        "evaluation_available": bool(ordered),
    }
