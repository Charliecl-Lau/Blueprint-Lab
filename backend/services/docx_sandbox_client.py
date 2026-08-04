from __future__ import annotations

import base64
import hashlib
import time
import uuid
from dataclasses import dataclass

import httpx

from backend.config import settings
from backend.schemas.docx_authoring_schema import DocxProgramEnvelope
from docx_sandbox.contracts import ExecuteResponse, ResultStatus, sha256_program


_JOB_NAMESPACE = uuid.UUID("73d62c66-ea77-4ae2-b55c-d391fc09073e")


class SandboxTransportError(RuntimeError):
    pass


class SandboxProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxExecutionResult:
    job_id: str
    status: str
    docx_bytes: bytes | None
    manifest: dict | None
    docx_sha256: str | None
    manifest_sha256: str | None
    image_digest: str
    evidence: dict
    issues: tuple[str, ...]

    @property
    def succeeded(self) -> bool:
        return self.status == ResultStatus.succeeded.value


def stable_job_id(run_id: int, cycle_number: int, attempt_number: int) -> str:
    return str(uuid.uuid5(_JOB_NAMESPACE, f"{run_id}:{cycle_number}:{attempt_number}"))


class DocxSandboxClient:
    def __init__(self, *, client=None):
        self.base_url = settings.docx_sandbox_url.rstrip("/")
        self.token = settings.docx_sandbox_service_token
        self.expected_image_digest = settings.docx_sandbox_expected_image_digest
        self.max_response_bytes = settings.docx_sandbox_max_response_bytes
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=settings.docx_sandbox_connect_timeout_seconds,
                read=settings.docx_sandbox_read_timeout_seconds,
                write=settings.docx_sandbox_connect_timeout_seconds,
                pool=settings.docx_sandbox_connect_timeout_seconds,
            )
        )

    def execute(
        self,
        *,
        job_id: str,
        cycle_number: int,
        attempt_number: int,
        envelope: DocxProgramEnvelope,
        grounding_sha256: str,
    ) -> SandboxExecutionResult:
        payload = {
            "job_id": job_id,
            "cycle_number": cycle_number,
            "attempt_number": attempt_number,
            "envelope_version": envelope.schema_version,
            "program": envelope.program,
            "program_sha256": sha256_program(envelope.program),
            "grounding_sha256": grounding_sha256,
        }
        response = None
        for transport_attempt in range(2):
            try:
                response = self.client.post(
                    self.base_url + "/v1/jobs",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                if response.status_code not in {429, 502, 503, 504}:
                    break
                if transport_attempt == 1:
                    raise SandboxTransportError(
                        f"DOCX sandbox unavailable ({response.status_code})"
                    )
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
                if transport_attempt == 1:
                    raise SandboxTransportError("DOCX sandbox transport failed") from exc
            time.sleep(0.05)
        if response is None:
            raise SandboxTransportError("DOCX sandbox returned no response")
        if len(response.content) > self.max_response_bytes:
            raise SandboxProtocolError("DOCX sandbox response exceeded configured limit")
        if response.status_code >= 500 or response.status_code == 429:
            raise SandboxTransportError(f"DOCX sandbox unavailable ({response.status_code})")
        if response.status_code != 200:
            raise SandboxProtocolError(f"DOCX sandbox rejected request ({response.status_code})")
        try:
            parsed = ExecuteResponse.model_validate(response.json())
        except Exception as exc:
            raise SandboxProtocolError("DOCX sandbox returned an invalid response") from exc
        if str(parsed.job_id) != job_id:
            raise SandboxProtocolError("DOCX sandbox job ID mismatch")
        image_digest = parsed.evidence.image_digest
        if self.expected_image_digest and image_digest != self.expected_image_digest:
            raise SandboxProtocolError("DOCX sandbox image digest mismatch")
        docx_bytes = (
            base64.b64decode(parsed.artifact_base64, validate=True)
            if parsed.artifact_base64 is not None
            else None
        )
        docx_hash = hashlib.sha256(docx_bytes).hexdigest() if docx_bytes is not None else None
        manifest_bytes = (
            base64.b64decode(parsed.manifest_base64, validate=True)
            if parsed.manifest_base64 is not None
            else None
        )
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest() if manifest_bytes is not None else None
        expected_hashes = parsed.evidence.output_sha256
        if docx_hash is not None and expected_hashes.get("assessment.docx") != docx_hash:
            raise SandboxProtocolError("DOCX sandbox artifact hash mismatch")
        if manifest_hash is not None and expected_hashes.get("assessment_manifest.json") != manifest_hash:
            raise SandboxProtocolError("DOCX sandbox manifest hash mismatch")
        if parsed.status is ResultStatus.succeeded and manifest_bytes is None:
            raise SandboxProtocolError("DOCX sandbox omitted manifest bytes")
        return SandboxExecutionResult(
            job_id=job_id,
            status=parsed.status.value,
            docx_bytes=docx_bytes,
            manifest=parsed.manifest_json,
            docx_sha256=docx_hash,
            manifest_sha256=manifest_hash,
            image_digest=image_digest,
            evidence=parsed.evidence.model_dump(),
            issues=tuple(parsed.issues),
        )
