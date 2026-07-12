import hashlib
from unittest.mock import patch

from backend.models.experiment import Condition, Experiment
from backend.models.run import Assessment, DocumentArtifact, Prompt, Run
from backend.models.source_document import SourceDocument


def test_unknown_run_and_condition_return_404(client):
    assert client.get("/runs/999999").status_code == 404
    assert client.post("/runs/999999/retry").status_code == 404
    assert client.post("/conditions/999999/runs", json={}).status_code == 404


def test_canonical_create_detail_retry_raw_and_export(client, test_db):
    experiment = Experiment(course="C", topic="T", learning_objectives="L", assessment_type="mixed", difficulty="D", number_of_questions=1)
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
    with patch("backend.api.runs.run_generation_pipeline.delay"):
        retried = client.post(f"/runs/{run_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["id"] != run_id


def test_create_rejects_caller_supplied_snapshot_hash(client, test_db):
    experiment = Experiment(course="C", topic="T", learning_objectives="L", assessment_type="mixed", difficulty="D", number_of_questions=1)
    test_db.add(experiment); test_db.flush()
    condition = Condition(experiment_id=experiment.id, prompt_structure="openai", factor_inputs={}, condition_label="test")
    source = SourceDocument(name="S", document_type="reference", version="1", original_filename="s.txt", media_type="text/plain", content=b"persisted", content_hash=hashlib.sha256(b"persisted").hexdigest(), extracted_text="persisted text")
    test_db.add_all([condition, source]); test_db.commit()
    response = client.post(f"/conditions/{condition.id}/runs", json={"source_bindings": [{"source_document_id": source.id, "role": "reference_content", "ordinal": 0, "included_text_hash": "0" * 64}]})
    assert response.status_code == 422
    assert test_db.query(Run).filter_by(condition_id=condition.id).count() == 0
