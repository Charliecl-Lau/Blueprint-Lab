import base64
import hashlib
import json
from types import SimpleNamespace

import httpx

from backend.schemas.docx_authoring_schema import DocxProgramEnvelope
from backend.services.docx_sandbox_client import DocxSandboxClient, stable_job_id


class FakeResponse:
    status_code = 200
    def __init__(self, value):
        self.value = value
        self.content = json.dumps(value).encode()
    def json(self): return self.value


class FakeHttpClient:
    def __init__(self, response): self.response, self.calls = response, []
    def post(self, *args, **kwargs): self.calls.append((args, kwargs)); return self.response


def test_sandbox_client_authenticates_and_verifies_output_hashes(monkeypatch):
    docx = b"docx"
    manifest = b'{"questions":[]}'
    job_id = stable_job_id(1, 1, 1)
    response = FakeResponse({
        "job_id": job_id, "status": "succeeded",
        "evidence": {"image_digest": "sha256:" + "a" * 64, "wall_time_ms": 10, "output_names": ["assessment.docx", "assessment_manifest.json"], "output_sizes": {"assessment.docx": len(docx), "assessment_manifest.json": len(manifest)}, "output_sha256": {"assessment.docx": hashlib.sha256(docx).hexdigest(), "assessment_manifest.json": hashlib.sha256(manifest).hexdigest()}, "stdout": "", "stderr": ""},
        "manifest_json": {"questions": []}, "manifest_base64": base64.b64encode(manifest).decode(), "artifact_base64": base64.b64encode(docx).decode(), "issues": [],
    })
    http = FakeHttpClient(response)
    client = DocxSandboxClient(client=http)
    client.token = "secret"
    client.expected_image_digest = "sha256:" + "a" * 64
    envelope = DocxProgramEnvelope(schema_version="docx-program-envelope/1", language="python", entrypoint="program.py", program="print('x')", expected_outputs=["assessment.docx", "assessment_manifest.json"], grounding_sha256="b" * 64, generation_notes="")
    result = client.execute(job_id=job_id, cycle_number=1, attempt_number=1, envelope=envelope, grounding_sha256="b" * 64)
    assert result.docx_sha256 == hashlib.sha256(docx).hexdigest()
    assert http.calls[0][1]["headers"]["Authorization"] == "Bearer secret"


def test_stable_job_id_is_replay_safe():
    assert stable_job_id(8, 2, 1) == stable_job_id(8, 2, 1)
    assert stable_job_id(8, 2, 1) != stable_job_id(8, 2, 2)
