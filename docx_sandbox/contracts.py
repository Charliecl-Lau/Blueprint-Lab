from __future__ import annotations
import base64
import hashlib
from enum import Enum
from typing import Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


def normalized_program_bytes(program: str) -> bytes:
    return program.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def sha256_program(program: str) -> str:
    return hashlib.sha256(normalized_program_bytes(program)).hexdigest()


class ResultStatus(str, Enum):
    succeeded = "succeeded"
    policy_rejected = "policy_rejected"
    timed_out = "timed_out"
    resource_exhausted = "resource_exhausted"
    execution_failed = "execution_failed"
    output_rejected = "output_rejected"


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    cycle_number: int = Field(ge=1)
    attempt_number: Literal[1, 2]
    envelope_version: Literal["docx-program-envelope/1"]
    program: str = Field(min_length=1, max_length=750_000)
    program_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    grounding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def hash_matches(self):
        if sha256_program(self.program) != self.program_sha256:
            raise ValueError("program_sha256 does not match normalized program bytes")
        return self


class ExecutionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_digest: str
    exit_code: Optional[int] = None
    wall_time_ms: int = Field(ge=0)
    termination_reason: Optional[str] = None
    output_names: List[str] = []
    output_sizes: Dict[str, int] = {}
    output_sha256: Dict[str, str] = {}
    stdout: str = ""
    stderr: str = ""


class ExecuteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    status: ResultStatus
    evidence: ExecutionEvidence
    manifest_json: Optional[dict] = None
    manifest_base64: Optional[str] = None
    artifact_base64: Optional[str] = None
    issues: List[str] = []

    @model_validator(mode="after")
    def artifact_only_on_success(self):
        if self.artifact_base64 is not None and self.status is not ResultStatus.succeeded:
            raise ValueError("artifact is only returned for successful executions")
        if self.artifact_base64 is not None:
            base64.b64decode(self.artifact_base64, validate=True)
        if self.manifest_base64 is not None:
            base64.b64decode(self.manifest_base64, validate=True)
        return self
