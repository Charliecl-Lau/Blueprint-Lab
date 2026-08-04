from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from backend.schemas.docx_authoring_schema import DocxProgramEnvelope
from backend.services.docx_grounding import DocxGrounding
from backend.services.llm_client import LLMResult


@dataclass(frozen=True)
class RepairContext:
    previous_program: str
    issues: tuple[dict, ...]
    stdout: str = ""
    stderr: str = ""

    @classmethod
    def from_report(cls, report, previous_program: str = "") -> "RepairContext":
        issues = tuple(
            issue.as_dict() if hasattr(issue, "as_dict") else dict(issue)
            for issue in report.issues
        )
        execution = getattr(report, "execution", {}) or {}
        return cls(
            previous_program=previous_program,
            issues=issues,
            stdout=str(execution.get("stdout", ""))[-8192:],
            stderr=str(execution.get("stderr", ""))[-8192:],
        )


@dataclass(frozen=True)
class AuthoringResult:
    envelope: DocxProgramEnvelope
    provider_result: LLMResult
    duration_ms: int
    prompt_sha256: str


class DocxAuthoringProvider(Protocol):
    def author_program(
        self,
        grounding: DocxGrounding,
        *,
        attempt_number: Literal[1, 2],
        repair_context: RepairContext | None = None,
    ) -> AuthoringResult: ...
