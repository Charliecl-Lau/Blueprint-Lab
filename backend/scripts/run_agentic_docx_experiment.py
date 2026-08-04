"""Write a content-free evidence report for an existing agentic DOCX run."""

import argparse
import json
from pathlib import Path

from backend.database import SessionLocal
from backend.models import Run


def build_report(run: Run) -> dict:
    session = max(run.docx_tool_sessions, key=lambda item: (item.cycle_number, item.id or 0), default=None)
    if session is None:
        raise ValueError("run has no agentic DOCX session")
    iterations = sorted(session.iterations, key=lambda item: item.iteration_number)
    actions = sorted(session.actions, key=lambda item: (item.iteration_id, item.sequence_number))
    artifact = run.canonical_assessment.document_artifact if run.canonical_assessment is not None else None
    usage = [item for item in run.model_call_usages if item.stage in {"docx_tool_design", "docx_visual_review"}]
    return {
        "run_id": run.id,
        "session_id": session.id,
        "provider": session.provider,
        "model": session.model,
        "content_catalog_hash": session.content_catalog_hash,
        "design_contract_hash": session.design_contract_hash,
        "workspace": {"revision": session.workspace_revision, "initial_hash": session.initial_workspace_hash, "final_hash": session.final_workspace_hash},
        "usage": [{"stage": item.stage, "attempt": item.attempt, "input_tokens": item.input_tokens, "output_tokens": item.output_tokens, "total_tokens": item.total_tokens} for item in usage],
        "tools": {"count": len(actions), "names": [item.tool_name for item in actions]},
        "renders": [{"iteration": item.iteration_number, "docx_hash": item.draft_docx_hash, "pdf_hash": item.draft_pdf_hash, "pages": item.page_image_metadata, "validators": item.validator_report, "decision": item.review_decision} for item in iterations],
        "final_decision": session.final_decision,
        "revision_budget_used": max(0, len(iterations) - 1),
        "artifact": {"hash": artifact.content_hash if artifact else None, "byte_size": len(artifact.content) if artifact else None},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--run-id", type=int, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv); db = SessionLocal()
    try:
        run = db.get(Run, args.run_id)
        if run is None: raise SystemExit("run not found")
        report = build_report(run)
    finally: db.close()
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__": raise SystemExit(main())
