from unittest.mock import patch, MagicMock

RUN_PAYLOAD = {
    "topic": "TCP/IP Networking",
    "expectations": "Test understanding of the three-way handshake",
    "mcq_count": 2,
    "long_answer_count": 1,
    "control_sets": [
        {"personality": "formal", "prompt_length": "short", "result_length": "short", "action_word_count": 2},
        {"personality": "socratic", "prompt_length": "medium", "result_length": "medium", "action_word_count": 3},
        {"personality": "encouraging", "prompt_length": "long", "result_length": "long", "action_word_count": 4},
        {"personality": "challenging", "prompt_length": "short", "result_length": "medium", "action_word_count": 1},
    ],
    "frameworks": ["forge", "openai", "risen"],
}

def test_get_run_not_found(client):
    response = client.get("/runs/999")
    assert response.status_code == 404

def test_get_run_returns_run(client, test_db):
    from backend.models.run import Run
    run = Run(topic="Test", expectations="Test", mcq_count=2, long_answer_count=1)
    test_db.add(run)
    test_db.commit()

    response = client.get(f"/runs/{run.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["topic"] == "Test"
    assert data["id"] == run.id
