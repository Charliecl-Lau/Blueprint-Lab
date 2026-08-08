def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_worker_health_reports_available_workers(client, monkeypatch):
    class Inspect:
        def ping(self):
            return {"celery@test": {"ok": "pong"}}

    monkeypatch.setattr(
        "backend.main.celery_app.control.inspect",
        lambda timeout: Inspect(),
    )

    response = client.get("/health/worker")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "workers": 1}


def test_worker_health_reports_unavailable_when_no_worker_replies(
    client, monkeypatch
):
    class Inspect:
        def ping(self):
            return None

    monkeypatch.setattr(
        "backend.main.celery_app.control.inspect",
        lambda timeout: Inspect(),
    )

    response = client.get("/health/worker")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "workers": 0}


def test_unrelated_request_validation_keeps_standard_fastapi_shape(client):
    response = client.get("/runs/not-an-integer")

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
