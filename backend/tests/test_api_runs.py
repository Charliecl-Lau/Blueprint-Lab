import hashlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest

from backend.models import ModelCallUsage
from backend.models.experiment import Condition, Experiment
from backend.models.experiment import utc_now
from backend.models.run import (
    Assessment,
    DocumentArtifact,
    Prompt,
    Run,
    RunReferencePdf,
)
from backend.models.source_document import SourceDocument
from backend.services.reference_pdfs import ProviderFileAttachment


def _experiment_and_condition(test_db, *, topic="Statics"):
    experiment = Experiment(
        course="C",
        topic=topic,
        learning_objectives=["L"],
        assessment_type="mixed",
        difficulty="D",
        number_of_questions=1,
    )
    condition = Condition(
        experiment=experiment,
        condition_code="C100",
        prompt_structure="openai",
        factor_inputs={},
        condition_label="Baseline",
    )
    test_db.add(experiment)
    test_db.flush()
    return experiment, condition


def _pdf_backed_run(test_db):
    experiment, condition = _experiment_and_condition(test_db)
    condition.reference_content_enabled = True
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="error",
        model_settings={},
    )
    run.reference_pdfs = [
        RunReferencePdf(ordinal=0, original_filename="old.pdf")
    ]
    test_db.add(run)
    test_db.commit()
    return run


def _attachment(number):
    return ProviderFileAttachment(
        name=f"files/{number}",
        uri=f"https://files/{number}",
        mime_type="application/pdf",
    )


@pytest.fixture
def run_with_usage(test_db):
    experiment, condition = _experiment_and_condition(test_db)
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="complete",
        model_settings={},
        input_tokens=30,
        output_tokens=12,
        total_tokens=42,
        model_call_count=2,
    )
    run.model_call_usages.extend(
        [
            ModelCallUsage(
                call_id="detail-a",
                stage="actual_prompt",
                attempt=1,
                status="response",
                provider_response_id="detail-r1",
                input_tokens=10,
                output_tokens=4,
                total_tokens=14,
                extra_token_counts={},
            ),
            ModelCallUsage(
                call_id="detail-b",
                stage="assessment",
                attempt=1,
                status="response",
                provider_response_id="detail-r2",
                input_tokens=20,
                output_tokens=8,
                total_tokens=28,
                extra_token_counts={},
            ),
        ]
    )
    test_db.add(run)
    test_db.commit()
    return run


@pytest.fixture
def recent_runs(test_db):
    experiment, condition = _experiment_and_condition(test_db, topic="Equilibrium")
    now = utc_now()
    oldest = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="complete",
        model_settings={},
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        model_call_count=1,
        created_at=now - timedelta(minutes=5),
        completed_at=now - timedelta(minutes=4),
    )
    newest = Run(
        experiment=experiment,
        condition=condition,
        run_number=2,
        status="generating",
        model_settings={},
        input_tokens=3,
        output_tokens=1,
        total_tokens=4,
        model_call_count=1,
        created_at=now,
    )
    test_db.add_all([oldest, newest])
    test_db.commit()
    return SimpleNamespace(oldest=oldest, newest=newest)


@pytest.fixture
def history_runs(test_db):
    now = utc_now()
    records = []
    for index, (status, topic) in enumerate([
        ("complete", "Completed topic"),
        ("complete_with_warnings", "Warning topic"),
        ("error", "Failed topic"),
        ("generating", "Generating topic"),
        ("pending", "Pending topic"),
    ]):
        experiment, condition = _experiment_and_condition(test_db, topic=topic)
        run = Run(
            experiment=experiment,
            condition=condition,
            run_number=1,
            status=status,
            model_settings={},
            created_at=now + timedelta(minutes=index),
            completed_at=(now + timedelta(minutes=index))
            if status.startswith("complete") else None,
        )
        test_db.add(run)
        records.append(run)
    test_db.commit()
    return records


def test_unknown_run_and_condition_return_404(client):
    assert client.get("/runs/999999").status_code == 404
    assert client.post("/runs/999999/retry").status_code == 404
    assert client.post("/conditions/999999/runs", json={}).status_code == 404
    assert (
        client.post("/assessments/999999/evaluations/llm/retry").status_code
        == 404
    )


def test_evaluation_retry_endpoint_reuses_viewer_ready_run(client, test_db):
    experiment, condition = _experiment_and_condition(test_db)
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="complete",
        model_settings={},
        input_tokens=28,
        output_tokens=8,
        total_tokens=36,
        model_call_count=2,
        viewer_ready_at=utc_now(),
        completed_at=utc_now(),
        progress_message="Complete",
    )
    run.assessment = Assessment(
        raw_response_text='{"questions": [{"body": "Saved"}]}',
        parsed_json={"questions": [{"body": "Saved"}]},
        output_hash="a" * 64,
        schema_version="1",
    )
    run.document_artifact = DocumentArtifact(
        filename="saved.docx",
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        content=b"docx",
    )
    test_db.add(run)
    test_db.commit()

    with patch(
        "backend.workers.evaluation_worker.run_llm_evaluation_pipeline.delay"
    ) as evaluation_delay:
        response = client.post(
            f"/assessments/{run.assessment.id}/evaluations/llm/retry"
        )

    assert response.status_code == 200
    assert response.json()["id"] == run.id
    assert response.json()["status"] == "complete"
    assert run.assessment.parsed_json == {"questions": [{"body": "Saved"}]}
    evaluation_delay.assert_called_once_with(run.id)


def test_canonical_create_detail_retry_raw_and_export(client, test_db):
    experiment = Experiment(course="C", topic="T", learning_objectives=["L"], assessment_type="mixed", difficulty="D", number_of_questions=1)
    test_db.add(experiment); test_db.flush()
    condition = Condition(experiment_id=experiment.id, prompt_structure="openai", factor_inputs={}, condition_label="test")
    test_db.add(condition); test_db.commit()
    with patch("backend.api.runs.run_generation_pipeline.delay") as delay:
        created = client.post(f"/conditions/{condition.id}/runs", json={})
    assert created.status_code == 200
    run_id = created.json()["id"]
    delay.assert_called_once_with(run_id)
    run = test_db.get(Run, run_id)
    run.request_id = "generation-request"
    run.version = "generation-version"
    run.finish_reason = "STOP"
    run.duration_ms = 456
    run.prompt = Prompt(
        prompt_structure="openai",
        structure_system_prompt="OpenAI structure rules",
        structure_input="Assessment Details: MSE202",
        actual_prompt="# Role\nAssessment generator",
        actual_prompt_hash="a" * 64,
        structure_prompt_version="2",
        actual_prompt_generator_version="2",
        structure_request_id="structure-request",
        structure_model="gemini",
        structure_model_version="structure-version",
        structure_finish_reason="STOP",
        structure_duration_ms=123,
        generation_context="Generate the assessment now.",
        generation_envelope_hash="b" * 64,
    )
    run.assessment = Assessment(raw_response_text="private raw", parsed_json={"questions": []}, output_hash=hashlib.sha256(b"private raw").hexdigest(), schema_version="1")
    run.document_artifact = DocumentArtifact(filename="run.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", content=b"docx")
    test_db.commit()
    default = client.get(f"/runs/{run_id}").json()
    assert "raw_response_text" not in default["assessment"]
    assert default["prompt"]["actual_prompt_hash"] == run.prompt.actual_prompt_hash
    assert default["prompt"]["structure_prompt_version"] == "2"
    assert default["prompt"]["generation_request_id"] == "generation-request"
    assert "structure_system_prompt" not in default["prompt"]
    assert "actual_prompt" not in default["prompt"]
    raw_detail = client.get(f"/runs/{run_id}?include_raw_response=true").json()
    assert raw_detail["assessment"]["raw_response_text"] == "private raw"
    assert raw_detail["prompt"]["structure_system_prompt"] == "OpenAI structure rules"
    assert raw_detail["prompt"]["structure_input"] == "Assessment Details: MSE202"
    assert raw_detail["prompt"]["actual_prompt"] == "# Role\nAssessment generator"
    assert raw_detail["prompt"]["generation_context"] == "Generate the assessment now."
    assert client.get(f"/runs/{run_id}/export-docx").content == b"docx"
    with patch("backend.api.runs.run_generation_pipeline.delay") as retry_delay:
        retried = client.post(f"/runs/{run_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["id"] != run_id
    retry_delay.assert_called_once_with(retried.json()["id"])


def test_direct_run_creation_rejects_pdf_enabled_condition(client, test_db):
    _, condition = _experiment_and_condition(test_db)
    condition.reference_content_enabled = True
    test_db.commit()

    with patch("backend.api.runs.run_generation_pipeline.delay") as delay:
        response = client.post(f"/conditions/{condition.id}/runs", json={})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "reference_pdfs_required"
    assert test_db.query(Run).filter_by(condition_id=condition.id).count() == 0
    delay.assert_not_called()


def test_pdf_backed_retry_without_fresh_files_returns_stable_409(client, test_db):
    run = _pdf_backed_run(test_db)

    response = client.post(f"/runs/{run.id}/retry")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "reference_pdfs_required"


def test_pdf_backed_retry_uploads_fresh_files_and_enqueues_metadata(client, test_db):
    run = _pdf_backed_run(test_db)
    first = _attachment("one")
    second = _attachment("two")
    with (
        patch("backend.api.runs.LLMClient") as llm_client,
        patch("backend.api.runs.run_generation_pipeline.delay") as delay,
    ):
        llm_client.return_value.upload_pdf.side_effect = [first, second]
        response = client.post(
            f"/runs/{run.id}/retry",
            files=[
                (
                    "reference_pdfs",
                    ("new-one.pdf", b"%PDF-1.7\none", "application/pdf"),
                ),
                (
                    "reference_pdfs",
                    ("new-two.pdf", b"%PDF-1.7\ntwo", "application/pdf"),
                ),
            ],
        )

    assert response.status_code == 200
    assert response.json()["reference_pdf_filenames"] == [
        "new-one.pdf",
        "new-two.pdf",
    ]
    delay.assert_called_once_with(
        response.json()["id"],
        [first.to_dict(), second.to_dict()],
    )
    test_db.refresh(run)
    assert run.reference_pdf_filenames == ["old.pdf"]


def test_pdf_retry_partial_upload_failure_cleans_provider_state(client, test_db):
    run = _pdf_backed_run(test_db)
    first = _attachment("one")
    with patch("backend.api.runs.LLMClient") as llm_client:
        llm = llm_client.return_value
        llm.upload_pdf.side_effect = [first, RuntimeError("provider unavailable")]
        response = client.post(
            f"/runs/{run.id}/retry",
            files=[
                (
                    "reference_pdfs",
                    ("new-one.pdf", b"%PDF-1.7\none", "application/pdf"),
                ),
                (
                    "reference_pdfs",
                    ("new-two.pdf", b"%PDF-1.7\ntwo", "application/pdf"),
                ),
            ],
        )

    assert response.status_code == 502
    llm.delete_file.assert_has_calls([call("files/one")])
    assert test_db.query(Run).filter_by(condition_id=run.condition_id).count() == 1


def test_pdf_retry_dispatch_failure_terminalizes_new_run_and_cleans_files(
    client, test_db
):
    original = _pdf_backed_run(test_db)
    uploaded = _attachment("dispatch")
    with (
        patch("backend.api.runs.LLMClient") as llm_client,
        patch(
            "backend.api.runs.run_generation_pipeline.delay",
            side_effect=RuntimeError("broker host internal-secret"),
        ),
    ):
        llm_client.return_value.upload_pdf.return_value = uploaded
        response = client.post(
            f"/runs/{original.id}/retry",
            files=[
                (
                    "reference_pdfs",
                    ("fresh.pdf", b"%PDF-1.7\nfresh", "application/pdf"),
                )
            ],
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "generation_dispatch_failed"
    runs = test_db.query(Run).filter_by(condition_id=original.condition_id).all()
    assert len(runs) == 2
    retried = next(run for run in runs if run.id != original.id)
    test_db.refresh(retried)
    assert retried.status == "error"
    assert retried.error_type == "generation_dispatch_error"
    assert retried.completed_at is not None
    assert "internal-secret" not in (retried.error_message or "")
    assert original.status == "error"
    llm_client.return_value.delete_file.assert_called_once_with("files/dispatch")


def test_run_detail_reports_reference_pdf_filenames(client, test_db):
    run = _pdf_backed_run(test_db)

    response = client.get(f"/runs/{run.id}")

    assert response.json()["reference_pdf_filenames"] == ["old.pdf"]


def test_create_rejects_caller_supplied_snapshot_hash(client, test_db):
    experiment = Experiment(course="C", topic="T", learning_objectives=["L"], assessment_type="mixed", difficulty="D", number_of_questions=1)
    test_db.add(experiment); test_db.flush()
    condition = Condition(experiment_id=experiment.id, prompt_structure="openai", factor_inputs={}, condition_label="test")
    source = SourceDocument(name="S", document_type="reference", version="1", original_filename="s.txt", media_type="text/plain", content=b"persisted", content_hash=hashlib.sha256(b"persisted").hexdigest(), extracted_text="persisted text")
    test_db.add_all([condition, source]); test_db.commit()
    response = client.post(f"/conditions/{condition.id}/runs", json={"source_bindings": [{"source_document_id": source.id, "role": "reference_content", "ordinal": 0, "included_text_hash": "0" * 64}]})
    assert response.status_code == 422
    assert test_db.query(Run).filter_by(condition_id=condition.id).count() == 0


def test_run_detail_exposes_totals_and_stage_breakdown(client, run_with_usage):
    body = client.get(f"/runs/{run_with_usage.id}").json()

    assert body["token_usage"] == {
        "input_tokens": 30,
        "output_tokens": 12,
        "total_tokens": 42,
        "model_calls": 2,
        "recording_state": "recorded",
        "stages": [
            {
                "stage": "actual_prompt",
                "input_tokens": 10,
                "output_tokens": 4,
                "total_tokens": 14,
                "model_calls": 1,
            },
            {
                "stage": "assessment",
                "input_tokens": 20,
                "output_tokens": 8,
                "total_tokens": 28,
                "model_calls": 1,
            },
        ],
    }


def test_legacy_and_active_runs_report_distinct_recording_states(client, test_db):
    experiment, condition = _experiment_and_condition(test_db)
    legacy = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="complete",
        model_settings={},
    )
    active = Run(
        experiment=experiment,
        condition=condition,
        run_number=2,
        status="generating",
        model_settings={},
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        model_call_count=0,
    )
    test_db.add_all([legacy, active])
    test_db.commit()

    legacy_usage = client.get(f"/runs/{legacy.id}").json()["token_usage"]
    active_usage = client.get(f"/runs/{active.id}").json()["token_usage"]
    assert legacy_usage["recording_state"] == "not_recorded"
    assert legacy_usage["total_tokens"] is None
    assert active_usage["recording_state"] == "in_progress"


def test_recent_runs_returns_active_and_completed_in_reverse_order(
    client, recent_runs
):
    body = client.get("/runs/recent?limit=10").json()

    assert [item["id"] for item in body] == [
        recent_runs.newest.id,
        recent_runs.oldest.id,
    ]
    assert body[0]["topic"] == "Equilibrium"
    assert body[0]["token_usage"]["recording_state"] == "in_progress"


def test_recent_runs_limit_is_bounded(client):
    assert client.get("/runs/recent?limit=0").status_code == 422
    assert client.get("/runs/recent?limit=51").status_code == 422


def test_history_recent_returns_terminal_runs_newest_first(client, history_runs):
    response = client.get("/runs/history/recent?limit=10")

    assert response.status_code == 200
    assert [item["topic"] for item in response.json()] == [
        "Failed topic",
        "Warning topic",
        "Completed topic",
    ]
    assert [item["display_status"] for item in response.json()] == [
        "failed",
        "completed",
        "completed",
    ]


def test_history_recent_filters_before_applying_limit(client, history_runs):
    body = client.get("/runs/history/recent?limit=2").json()

    assert [item["topic"] for item in body] == ["Failed topic", "Warning topic"]


@pytest.mark.parametrize("limit", [0, 51])
def test_history_recent_rejects_invalid_limit(client, limit):
    assert client.get(f"/runs/history/recent?limit={limit}").status_code == 422


def _recoverable_payload(body: str):
    return {
        "questions": [
            {
                "type": "short_answer",
                "metadata": {
                    "question_title": "Component fractions",
                    "question_type": "short_answer",
                    "difficulty_level": "introductory",
                    "mse202_concepts": ["Mixtures"],
                    "mse302_concepts": ["Solutions"],
                    "concept_map_bridge": "Not Provided",
                    "materials_science_context": "Alloy solution.",
                    "estimated_time_minutes": 10,
                    "learning_objectives": ["Compare component fractions."],
                },
                "body": body,
                "model_answer": "Use x_A.",
                "equations": [],
                "revision_options": ["Add data.", "Explain assumptions."],
            }
        ]
    }


def test_recover_assessment_repairs_saved_component_tokens(client, test_db):
    import json

    experiment, condition = _experiment_and_condition(test_db)
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="error",
        model_settings={},
        error_type="assessment_parse_error",
    )
    run.assessment = Assessment(
        raw_response_text=json.dumps(_recoverable_payload("Compare x_B.")),
        parsed_json=None,
        output_hash="b" * 64,
        schema_version="1",
        validation_status="invalid",
    )
    test_db.add(run)
    test_db.commit()

    with (
        patch("backend.api.runs.save_assessment_artifact"),
        patch("backend.api.runs.run_llm_evaluation_pipeline.delay") as delay,
    ):
        response = client.post(f"/runs/{run.id}/recover-assessment")

    assert response.status_code == 200
    assert response.json()["status"] == "complete"
    assert response.json()["assessment"]["validation"]["status"] == "valid"
    assert response.json()["assessment"]["parsed_json"]["questions"][0]["body"] == (
        "Compare [[EQ:auto_q1_body_x_b_1]]."
    )
    delay.assert_called_once_with(run.id)


def test_recover_assessment_exposes_renderable_warnings(client, test_db):
    import json

    experiment, condition = _experiment_and_condition(test_db)
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="error",
        model_settings={},
        error_type="assessment_parse_error",
    )
    run.assessment = Assessment(
        raw_response_text=json.dumps(_recoverable_payload("Use G = H - T S.")),
        parsed_json=None,
        output_hash="c" * 64,
        schema_version="1",
        validation_status="invalid",
    )
    test_db.add(run)
    test_db.commit()

    response = client.post(f"/runs/{run.id}/recover-assessment")

    assert response.status_code == 200
    assert response.json()["status"] == "complete_with_warnings"
    assert response.json()["viewer_available"] is True
    validation = response.json()["assessment"]["validation"]
    assert validation["status"] == "warning"
    assert validation["acceptance_required"] is True
    assert response.json()["artifact_available"] is False


def test_accept_warning_assessment_enables_evaluation(client, test_db):
    experiment, condition = _experiment_and_condition(test_db)
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="complete_with_warnings",
        model_settings={},
    )
    run.prompt = Prompt(
        prompt_structure="openai",
        structure_system_prompt="rules",
        structure_input="input",
        actual_prompt="prompt",
        actual_prompt_hash="a" * 64,
        structure_prompt_version="4",
        actual_prompt_generator_version="11",
        generation_envelope_hash="b" * 64,
    )
    run.assessment = Assessment(
        raw_response_text='{"questions": []}',
        parsed_json={"questions": []},
        output_hash="d" * 64,
        schema_version="1",
        validation_status="warning",
        validation_issues=[{"message": "Unresolved equation"}],
    )
    test_db.add(run)
    test_db.commit()

    with (
        patch("backend.api.runs.save_assessment_artifact"),
        patch("backend.api.runs.run_llm_evaluation_pipeline.delay") as delay,
    ):
        response = client.post(f"/runs/{run.id}/accept-assessment-defects")

    assert response.status_code == 200
    assert response.json()["status"] == "complete_with_warnings"
    assert response.json()["assessment"]["validation"]["acceptance_required"] is False
    assert response.json()["assessment"]["validation"]["defects_accepted_at"] is not None
    delay.assert_called_once_with(run.id)
