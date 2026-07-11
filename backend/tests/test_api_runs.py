import hashlib
from unittest.mock import patch

from backend.models.experiment import Condition, Experiment
from backend.models.run import Assessment, DocumentArtifact, Run
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
    run.assessment = Assessment(raw_response_text="private raw", parsed_json={"questions": []}, output_hash=hashlib.sha256(b"private raw").hexdigest(), schema_version="1")
    run.document_artifact = DocumentArtifact(filename="run.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", content=b"docx")
    test_db.commit()
    default = client.get(f"/runs/{run_id}").json()
    assert "raw_response_text" not in default["assessment"]
    assert client.get(f"/runs/{run_id}?include_raw_response=true").json()["assessment"]["raw_response_text"] == "private raw"
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
