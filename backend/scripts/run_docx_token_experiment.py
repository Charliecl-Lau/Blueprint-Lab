from __future__ import annotations

import argparse
import csv
import io
import json
import uuid
from collections import defaultdict
from pathlib import Path

from backend.database import SessionLocal
from backend.models import Run
from backend.services.docx_grounding import GroundingError, build_docx_grounding


TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_content_tokens",
    "reasoning_tokens",
    "total_tokens",
)


def _milliseconds(start, end):
    if start is None or end is None:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def _attempt_for_usage(run: Run, usage_id: int | None):
    return next(
        (
            attempt
            for attempt in run.docx_authoring_attempts
            if attempt.model_call_usage_id == usage_id
        ),
        None,
    )


def _safe_duration(report: dict, *paths: tuple[str, ...]):
    for path in paths:
        value = report
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            return int(value)
    return None


def build_report(run: Run) -> dict:
    """Build a redacted measurement report from persisted run evidence."""
    calls = []
    grouped: dict[str, dict] = defaultdict(
        lambda: {field: 0 for field in TOKEN_FIELDS}
        | {"model_calls": 0, "attempts": []}
    )
    for usage in sorted(run.model_call_usages, key=lambda item: item.id or 0):
        attempt = _attempt_for_usage(run, usage.id)
        provider = attempt.provider if attempt is not None else run.provider
        model = attempt.model if attempt is not None else run.model
        model_version = attempt.model_version if attempt is not None else run.version
        call = {
            "stage": usage.stage,
            "attempt": usage.attempt,
            "provider": provider,
            "model": model,
            "model_version": model_version,
            **{field: getattr(usage, field) for field in TOKEN_FIELDS},
        }
        calls.append(call)
        stage = grouped[usage.stage]
        stage["model_calls"] += 1
        stage["attempts"].append(usage.attempt)
        for field in TOKEN_FIELDS:
            value = getattr(usage, field)
            if value is not None:
                stage[field] += value

    attempts = sorted(
        run.docx_authoring_attempts,
        key=lambda item: (item.cycle_number, item.attempt_number, item.id or 0),
    )
    latest_cycle = max((item.cycle_number for item in attempts), default=None)
    cycle_attempts = [item for item in attempts if item.cycle_number == latest_cycle]
    authoring_durations = {
        ("repair" if item.attempt_number == 2 else "initial"): _milliseconds(
            item.created_at, item.completed_at
        )
        for item in cycle_attempts
    }
    latest = cycle_attempts[-1] if cycle_attempts else None
    execution_report = latest.execution_report if latest is not None else {}
    validation_report = latest.validation_report if latest is not None else {}
    grounding_hash = latest.grounding_hash if latest is not None else None
    grounding_bytes = None
    try:
        grounding = build_docx_grounding(run)
        grounding_hash = grounding_hash or grounding.sha256
        grounding_bytes = len(grounding.canonical_bytes)
    except (GroundingError, OSError, ValueError):
        pass

    canonical = run.canonical_assessment
    artifact = canonical.document_artifact if canonical is not None else None
    return {
        "run_id": run.id,
        "experiment_id": run.experiment_id,
        "condition_id": run.condition_id,
        "run_number": run.run_number,
        "status": run.status,
        "model": run.model,
        "model_version": run.version,
        "calls": calls,
        "stages": dict(grouped),
        "total_end_to_end_model_tokens": run.total_tokens,
        "durations_ms": {
            "authoring_initial": authoring_durations.get("initial"),
            "authoring_repair": authoring_durations.get("repair"),
            "sandbox_execution": _safe_duration(
                execution_report,
                ("evidence", "wall_time_ms"),
                ("evidence", "duration_ms"),
                ("duration_ms",),
            ),
            "render": _safe_duration(
                validation_report,
                ("render_duration_ms",),
                ("render", "duration_ms"),
            ),
        },
        "grounding": {
            "byte_size": grounding_bytes,
            "sha256": grounding_hash,
        },
        "artifact": {
            "byte_size": len(bytes(artifact.content)) if artifact is not None else None,
            "page_count": validation_report.get("rendered_page_count"),
            "validation_outcome": validation_report.get("valid"),
        },
        "repair_used": any(item.attempt_number == 2 for item in cycle_attempts),
        "decision": None,
    }


def report_as_csv(reports: list[dict]) -> str:
    output = io.StringIO(newline="")
    fields = [
        "run_id", "experiment_id", "condition_id", "stage", "attempt",
        "provider", "model", "model_version", *TOKEN_FIELDS,
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for report in reports:
        for call in report["calls"]:
            writer.writerow({
                "run_id": report["run_id"],
                "experiment_id": report["experiment_id"],
                "condition_id": report["condition_id"],
                **call,
            })
    return output.getvalue()


def _execute_live_retry(db, run: Run) -> None:
    if run.status != "rewrite_failed":
        raise SystemExit(
            f"Run {run.id} is not rewrite_failed; live mode never creates or replaces a run automatically."
        )
    from backend.services.docx_rewrite_retry_service import request_docx_rewrite
    from backend.workers.assessment_worker import run_docx_rewrite_pipeline

    key = f"token-experiment-{uuid.uuid4()}"
    _, should_execute = request_docx_rewrite(db, run.id, key)
    if should_execute:
        run_docx_rewrite_pipeline.run(run.id, key)
        db.expire_all()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write a redacted DOCX token experiment report."
    )
    parser.add_argument("--run-id", type=int, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Explicitly start a new rewrite cycle for each eligible failed run before reporting.",
    )
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        runs = []
        for run_id in args.run_id:
            run = db.get(Run, run_id)
            if run is None:
                raise SystemExit(f"Run {run_id} was not found.")
            if args.execute_live:
                _execute_live_retry(db, run)
                run = db.get(Run, run_id)
            runs.append(run)
        reports = [build_report(run) for run in runs]
    finally:
        db.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = (
        report_as_csv(reports)
        if args.format == "csv"
        else json.dumps(reports[0] if len(reports) == 1 else reports, indent=2)
    )
    args.output.write_text(content, encoding="utf-8", newline="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
