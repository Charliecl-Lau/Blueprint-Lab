def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unrelated_request_validation_keeps_standard_fastapi_shape(client):
    response = client.get("/runs/not-an-integer")

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
