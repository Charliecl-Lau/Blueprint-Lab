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
