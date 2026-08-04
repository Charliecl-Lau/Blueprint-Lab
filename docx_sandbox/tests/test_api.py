from fastapi.testclient import TestClient
from docx_sandbox.api import app, _completed
from docx_sandbox.config import get_settings

def test_health_does_not_expose_service_secret(monkeypatch):
    get_settings.cache_clear(); monkeypatch.setenv("DOCX_SANDBOX_JOB_IMAGE_DIGEST", "sha256:"+"a"*64); monkeypatch.setenv("DOCX_SANDBOX_SERVICE_TOKEN", "secret")
    body = TestClient(app).get("/health").json()
    assert body["job_image_digest"].startswith("sha256:") and "secret" not in str(body)

def test_missing_auth_is_rejected(monkeypatch):
    get_settings.cache_clear(); monkeypatch.setenv("DOCX_SANDBOX_JOB_IMAGE_DIGEST", "sha256:"+"a"*64); monkeypatch.setenv("DOCX_SANDBOX_SERVICE_TOKEN", "secret")
    assert TestClient(app).post("/v1/jobs", json={}).status_code == 401
