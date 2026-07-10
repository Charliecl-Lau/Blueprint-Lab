from unittest.mock import patch


PAYLOAD = {
    "course": "ENGR 101",
    "topic": "Statics",
    "learning_objectives": "Solve equilibrium problems.",
    "assessment_type": "mixed",
    "difficulty": "introductory",
    "number_of_questions": 2,
    "estimated_time_minutes": 30,
    "prompt_structure": "openai",
    "factors": {"concept_bridge": True, "few_shot": False, "reference_content": True, "reasoning_guidance": False},
    "factor_inputs": {"concept_bridge": "Connect vectors to equilibrium.", "reference_content": "Use SI units."},
}


def test_create_experiment_creates_condition_and_generation(client):
    with patch("backend.api.experiments.run_generation_pipeline.delay") as delay:
        response = client.post("/experiments", json=PAYLOAD)

    assert response.status_code == 200
    data = response.json()
    assert data["course"] == "ENGR 101"
    assert data["estimated_time_minutes"] == 30
    assert data["conditions"][0]["factor_inputs"]["reference_content"] == "Use SI units."
    assert data["conditions"][0]["condition_label"] == "ConceptBridge=ON; FewShot=OFF; ReferenceContent=ON; ReasoningGuidance=OFF"
    assert data["generations"][0]["status"] == "pending"
    delay.assert_called_once_with(data["generations"][0]["id"])


def test_get_experiment_returns_generations(client):
    with patch("backend.api.experiments.run_generation_pipeline.delay"):
        created = client.post("/experiments", json=PAYLOAD).json()

    response = client.get(f"/experiments/{created['id']}")

    assert response.status_code == 200
    assert len(response.json()["generations"]) == 1


def test_get_missing_experiment_returns_404(client):
    response = client.get("/experiments/999999")

    assert response.status_code == 404
