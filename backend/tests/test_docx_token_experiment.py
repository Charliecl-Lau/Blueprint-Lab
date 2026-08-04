import csv
import hashlib
import io
import json

from backend.models import Assessment, DocxAuthoringAttempt, DocumentArtifact, ModelCallUsage
from backend.models.experiment import Condition, Experiment, utc_now
from backend.models.run import Run
from backend.scripts.run_docx_token_experiment import build_report, report_as_csv


def reported_run(db):
    experiment = Experiment(course="MSE", topic="Diffusion", learning_objectives=["Solve"], assessment_type="mcq", difficulty="medium", number_of_questions=1)
    condition = Condition(experiment=experiment, prompt_structure="openai", factor_inputs={}, condition_label="Experiment")
    run = Run(experiment=experiment, condition=condition, run_number=1, status="complete", provider="google", model="gemini-3.5-flash-lite", version="2026-08", model_settings={}, input_tokens=40, output_tokens=20, total_tokens=60, model_call_count=2)
    original = Assessment(version=1, kind="original_generation", raw_response_text="original secret", parsed_json={"questions": [{"body": "secret question"}]}, output_hash=hashlib.sha256(b"original secret").hexdigest(), schema_version="1")
    rewrite = Assessment(version=2, kind="full_rewrite", source_assessment=original, raw_response_text="rewritten secret", parsed_json={"questions": [{"body": "rewritten secret"}]}, output_hash=hashlib.sha256(b"rewritten secret").hexdigest(), schema_version="rewritten-assessment/1")
    run.assessment_versions.extend([original, rewrite]); run.canonical_assessment = rewrite
    rewrite.document_artifact = DocumentArtifact(run=run, filename="assessment.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", content=b"PK-docx-bytes")
    usage1 = ModelCallUsage(call_id="assessment-call", stage="assessment", attempt=1, status="response", provider_response_id="r1", input_tokens=10, output_tokens=5, total_tokens=15, cached_content_tokens=2, reasoning_tokens=1, extra_token_counts={})
    usage2 = ModelCallUsage(call_id="docx-call", stage="docx_code_generation", attempt=1, status="response", provider_response_id="r2", input_tokens=30, output_tokens=15, total_tokens=45, cached_content_tokens=0, reasoning_tokens=4, extra_token_counts={})
    run.model_call_usages.extend([usage1, usage2]); db.add(run); db.flush()
    now = utc_now()
    run.docx_authoring_attempts.append(DocxAuthoringAttempt(source_assessment_id=original.id, cycle_number=1, attempt_number=1, status="succeeded", provider="google", model="gemini-3.5-flash-lite", model_version="2026-08", model_call_usage_id=usage2.id, prompt_hash="a" * 64, grounding_hash="b" * 64, program_text="SECRET PROGRAM", envelope={"program": "SECRET PROGRAM"}, execution_report={"evidence": {"duration_ms": 120}}, validation_report={"valid": True, "rendered_page_count": 2, "render_duration_ms": 80}, created_at=now, completed_at=now))
    db.commit()
    return run


def test_report_is_machine_readable_complete_and_redacted(test_db):
    run = reported_run(test_db)
    report = build_report(run)

    assert report["run_id"] == run.id
    assert report["condition_id"] == run.condition_id
    assert report["stages"]["docx_code_generation"]["total_tokens"] == 45
    assert report["calls"][1]["model"] == "gemini-3.5-flash-lite"
    assert report["total_end_to_end_model_tokens"] == 60
    assert report["grounding"]["sha256"] == "b" * 64
    assert report["artifact"]["byte_size"] == len(b"PK-docx-bytes")
    assert report["artifact"]["page_count"] == 2
    assert report["repair_used"] is False
    assert report["decision"] is None
    encoded = json.dumps(report)
    assert "secret" not in encoded.lower()
    assert "program" not in encoded.lower()


def test_csv_report_contains_stage_attempt_rows(test_db):
    run = reported_run(test_db)
    rows = list(csv.DictReader(io.StringIO(report_as_csv([build_report(run)]))))
    assert [row["stage"] for row in rows] == ["assessment", "docx_code_generation"]
    assert rows[1]["attempt"] == "1"
