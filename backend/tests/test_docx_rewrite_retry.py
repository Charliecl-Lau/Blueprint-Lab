import hashlib
from unittest.mock import patch

from backend.models import Assessment, DocxAuthoringAttempt
from backend.models.experiment import Condition, Experiment
from backend.models.run import Prompt, Run


def failed_run(db):
    experiment = Experiment(
        course="MSE",
        topic="Phases",
        learning_objectives=["Analyze"],
        assessment_type="mcq",
        difficulty="medium",
        number_of_questions=1,
    )
    condition = Condition(
        experiment=experiment,
        prompt_structure="openai",
        factor_inputs={},
        condition_label="Baseline",
    )
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="rewrite_failed",
        model="gemini-3.5-flash-lite",
        model_settings={},
        execution_config={},
    )
    run.prompt = Prompt(
        actual_prompt="Actual",
        actual_prompt_hash=hashlib.sha256(b"Actual").hexdigest(),
        prompt_structure="openai",
        structure_system_prompt="system",
        structure_input="input",
        structure_prompt_version="v1",
        actual_prompt_generator_version="v1",
        generation_context="",
        execution_system_prompt="",
        execution_user_message="",
        execution_schema_version="1",
        generation_envelope_hash="b" * 64,
    )
    original = Assessment(
        version=1,
        kind="original_generation",
        raw_response_text="original",
        parsed_json={"questions": [{"id": "q1", "body": "Original"}]},
        parsed_json_hash=None,
        output_hash=hashlib.sha256(b"original").hexdigest(),
        schema_version="1",
    )
    run.assessment = original
    db.add(run)
    db.commit()
    return run, original


def test_retry_endpoint_requires_failed_run_and_is_idempotent(client, test_db):
    run, original = failed_run(test_db)
    headers = {"Idempotency-Key": "operator-request-1"}

    with patch("backend.api.runs.run_docx_rewrite_pipeline.delay") as delay:
        first = client.post(f"/runs/{run.id}/docx-rewrite/retry", headers=headers)
        duplicate = client.post(f"/runs/{run.id}/docx-rewrite/retry", headers=headers)

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert first.json()["id"] == run.id
    assert first.json()["status"] == "docx_authoring"
    assert first.json()["rewrite"]["canonical_assessment_id"] == original.id
    delay.assert_called_once_with(run.id, "operator-request-1")
    attempts = test_db.query(DocxAuthoringAttempt).filter_by(run_id=run.id).all()
    assert [(item.cycle_number, item.attempt_number, item.status) for item in attempts] == [
        (1, 1, "requested")
    ]
    assert run.assessment_versions == [original]


def test_retry_endpoint_rejects_unknown_ineligible_and_missing_key(client, test_db):
    assert client.post(
        "/runs/999999/docx-rewrite/retry",
        headers={"Idempotency-Key": "unknown"},
    ).status_code == 404
    run, _ = failed_run(test_db)
    assert client.post(f"/runs/{run.id}/docx-rewrite/retry").status_code == 422
    run.status = "complete"
    test_db.commit()
    assert client.post(
        f"/runs/{run.id}/docx-rewrite/retry",
        headers={"Idempotency-Key": "ineligible"},
    ).status_code == 409
