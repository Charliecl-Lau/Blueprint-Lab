from unittest.mock import patch

from backend.models import Experiment, Run


def valid_payload():
    return {
        "course": "ENGR 101",
        "topic": "Statics",
        "learning_objectives": "Solve equilibrium problems.",
        "assessment_type": "mixed",
        "difficulty": "introductory",
        "number_of_questions": 2,
        "estimated_time_minutes": 30,
        "prompt_structure": "openai",
        "factors": {
            "concept_bridge": True,
            "few_shot": False,
            "reference_content": True,
            "reasoning_guidance": False,
        },
        "factor_inputs": {
            "concept_bridge": "Connect vectors to equilibrium.",
            "reference_content": "Use SI units.",
        },
    }


def incomplete_payload():
    return {
        **valid_payload(),
        "course": "",
        "topic": "",
        "learning_objectives": "",
    }


def test_create_experiment_creates_condition_and_generation(client):
    with patch("backend.api.experiments.run_generation_pipeline.delay") as delay:
        response = client.post(
            "/experiments",
            headers={"Idempotency-Key": "create-1"},
            json=valid_payload(),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["course"] == "ENGR 101"
    assert data["estimated_time_minutes"] == 30
    assert data["conditions"][0]["factor_inputs"]["reference_content"] == "Use SI units."
    assert data["conditions"][0]["condition_label"] == "ConceptBridge=ON; FewShot=OFF; ReferenceContent=ON; ReasoningGuidance=OFF"
    assert data["generations"][0]["status"] == "pending"
    assert data["runs"] == data["generations"]
    delay.assert_called_once_with(data["generations"][0]["id"])


def test_get_experiment_returns_generations(client):
    with patch("backend.api.experiments.run_generation_pipeline.delay"):
        created = client.post(
            "/experiments",
            headers={"Idempotency-Key": "create-for-get"},
            json=valid_payload(),
        ).json()

    response = client.get(f"/experiments/{created['id']}")

    assert response.status_code == 200
    assert len(response.json()["generations"]) == 1


def test_get_missing_experiment_returns_404(client):
    response = client.get("/experiments/999999")

    assert response.status_code == 404


def test_duplicate_idempotency_key_returns_one_run_and_enqueues_once(client):
    with patch("backend.api.experiments.run_generation_pipeline.delay") as delay:
        first = client.post(
            "/experiments",
            headers={"Idempotency-Key": "submission-1"},
            json=valid_payload(),
        )
        second = client.post(
            "/experiments",
            headers={"Idempotency-Key": "submission-1"},
            json=valid_payload(),
        )

    assert first.status_code == second.status_code == 200
    assert first.json()["runs"][0]["id"] == second.json()["runs"][0]["id"]
    delay.assert_called_once()


def test_invalid_request_creates_nothing_and_enqueues_nothing(client, test_db):
    with patch("backend.api.experiments.run_generation_pipeline.delay") as delay:
        response = client.post(
            "/experiments",
            headers={"Idempotency-Key": "invalid"},
            json=incomplete_payload(),
        )

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
    missing = client.post("/experiments", json=valid_payload())
    blank = client.post(
        "/experiments",
        headers={"Idempotency-Key": "   "},
        json=valid_payload(),
    )

    assert missing.status_code == 422
    assert blank.status_code == 422
