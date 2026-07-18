import json
from unittest.mock import call, patch

from backend.models import Experiment, Run, SourceDocument
from backend.services.reference_pdfs import ProviderFileAttachment


def valid_payload():
    return {
        "course": "ENGR 101",
        "topic": "Statics",
        "learning_objectives": "Solve equilibrium problems.",
        "assessment_type": "mixed",
        "difficulty": "introductory",
        "number_of_questions": 2,
        "estimated_time_minutes": 30,
        "cognitive_demand": "evaluate_create",
        "additional_instruction": "Use one laboratory scenario.",
        "prompt_structure": "openai",
        "factors": {
            "concept_bridge": True,
            "few_shot": False,
            "reference_content": True,
            "reasoning_guidance": False,
        },
        "factor_inputs": {
            "concept_bridge": "Connect vectors to equilibrium.",
        },
    }


def pdf_file(name="reference.pdf", content=b"%PDF-1.7\nvalid"):
    return name, content, "application/pdf"


def post_experiment(client, key, payload=None, pdfs=None):
    files = [
        ("reference_pdfs", pdf)
        for pdf in (pdfs if pdfs is not None else [pdf_file()])
    ]
    return client.post(
        "/experiments",
        headers={"Idempotency-Key": key},
        data={"payload": json.dumps(payload or valid_payload())},
        files=files or None,
    )


def attachment(number):
    return ProviderFileAttachment(
        name=f"files/{number}",
        uri=f"https://files/{number}",
        mime_type="application/pdf",
    )


def incomplete_payload():
    return {
        **valid_payload(),
        "course": "",
        "topic": "",
        "learning_objectives": "",
    }


def test_create_experiment_creates_condition_and_generation(client, test_db):
    first = attachment("one")
    second = attachment("two")
    with (
        patch("backend.api.experiments.LLMClient") as llm_client,
        patch("backend.api.experiments.run_generation_pipeline.delay") as delay,
    ):
        llm_client.return_value.upload_pdf.side_effect = [first, second]
        response = post_experiment(
            client,
            "create-1",
            pdfs=[pdf_file("one.pdf"), pdf_file("two.pdf")],
        )

    assert response.status_code == 200
    data = response.json()
    assert data["course"] == "ENGR 101"
    assert data["estimated_time_minutes"] == 30
    assert data["cognitive_demand"] == "evaluate_create"
    assert data["additional_instruction"] == "Use one laboratory scenario."
    assert "reference_content" not in data["conditions"][0]["factor_inputs"]
    assert data["conditions"][0]["condition_label"] == "ConceptBridge=ON; FewShot=OFF; ReferenceContent=ON; ReasoningGuidance=OFF"
    assert data["generations"][0]["status"] == "pending"
    assert data["runs"][0]["reference_pdf_filenames"] == ["one.pdf", "two.pdf"]
    assert data["runs"] == data["generations"]
    delay.assert_called_once_with(
        data["generations"][0]["id"],
        [first.to_dict(), second.to_dict()],
    )
    assert test_db.query(SourceDocument).count() == 0


def test_get_experiment_returns_generations(client, test_db):
    with (
        patch("backend.api.experiments.LLMClient") as llm_client,
        patch("backend.api.experiments.run_generation_pipeline.delay"),
    ):
        llm_client.return_value.upload_pdf.return_value = attachment("get")
        created = post_experiment(client, "create-for-get").json()

    run = test_db.get(Run, created["runs"][0]["id"])
    run.viewer_ready_at = run.created_at
    run.progress_message = "Preparing generated assessment for evaluation"
    test_db.commit()
    response = client.get(f"/experiments/{created['id']}")

    assert response.status_code == 200
    assert len(response.json()["generations"]) == 1
    assert response.json()["cognitive_demand"] == "evaluate_create"
    assert response.json()["additional_instruction"] == "Use one laboratory scenario."
    assert response.json()["runs"][0]["viewer_ready_at"] is not None
    assert response.json()["runs"][0]["progress_message"] == (
        "Preparing generated assessment for evaluation"
    )


def test_get_missing_experiment_returns_404(client):
    response = client.get("/experiments/999999")

    assert response.status_code == 404


def test_duplicate_idempotency_key_returns_one_run_and_enqueues_once(client):
    with (
        patch("backend.api.experiments.LLMClient") as llm_client,
        patch("backend.api.experiments.run_generation_pipeline.delay") as delay,
    ):
        llm_client.return_value.upload_pdf.return_value = attachment("duplicate")
        first = post_experiment(client, "submission-1")
        second = post_experiment(client, "submission-1")

    assert first.status_code == second.status_code == 200
    assert first.json()["runs"][0]["id"] == second.json()["runs"][0]["id"]
    delay.assert_called_once()
    llm_client.return_value.upload_pdf.assert_called_once()


def test_invalid_request_creates_nothing_and_enqueues_nothing(client, test_db):
    with patch("backend.api.experiments.run_generation_pipeline.delay") as delay:
        response = post_experiment(client, "invalid", incomplete_payload())

    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0].keys() == {
        "section",
        "field",
        "label",
        "message",
    }
    assert test_db.query(Experiment).count() == 0
    assert test_db.query(Run).count() == 0
    delay.assert_not_called()


def test_create_requires_nonblank_idempotency_key(client):
    request = {
        "data": {"payload": json.dumps(valid_payload())},
        "files": [("reference_pdfs", pdf_file())],
    }
    missing = client.post("/experiments", **request)
    blank = client.post(
        "/experiments", headers={"Idempotency-Key": "   "}, **request
    )

    assert missing.status_code == 422
    assert blank.status_code == 422


def test_reference_content_requires_pdf_files(client):
    with patch("backend.api.experiments.LLMClient") as llm_client:
        response = post_experiment(client, "missing-pdfs", pdfs=[])

    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["field"] == "reference_pdfs"
    llm_client.assert_not_called()


def test_rejects_pdf_files_when_reference_content_is_disabled(client):
    payload = valid_payload()
    payload["factors"]["reference_content"] = False
    with patch("backend.api.experiments.LLMClient") as llm_client:
        response = post_experiment(client, "disabled-pdfs", payload)

    assert response.status_code == 422
    llm_client.assert_not_called()


def test_rejects_too_many_or_invalid_pdf_files_before_upload(client):
    with patch("backend.api.experiments.LLMClient") as llm_client:
        too_many = post_experiment(
            client,
            "too-many",
            pdfs=[pdf_file(f"{index}.pdf") for index in range(4)],
        )
        invalid = post_experiment(
            client,
            "invalid-pdf",
            pdfs=[pdf_file(content=b"not a pdf")],
        )

    assert too_many.status_code == 422
    assert invalid.status_code == 422
    llm_client.assert_not_called()


def test_partial_provider_upload_failure_deletes_uploaded_files(client, test_db):
    first = attachment("one")
    with patch("backend.api.experiments.LLMClient") as llm_client:
        llm = llm_client.return_value
        llm.upload_pdf.side_effect = [first, RuntimeError("provider unavailable")]

        response = post_experiment(
            client,
            "partial-upload",
            pdfs=[pdf_file("one.pdf"), pdf_file("two.pdf")],
        )

    assert response.status_code == 502
    llm.delete_file.assert_has_calls([call("files/one")])
    assert test_db.query(Experiment).count() == 0
