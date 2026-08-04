from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VerificationIssue:
    code: str
    severity: str = "error"
    repairable: bool = True
    evidence: str = ""

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "repairable": self.repairable,
            "evidence": self.evidence[:1000],
        }


@dataclass(frozen=True)
class VerificationReport:
    valid: bool
    issues: tuple[VerificationIssue, ...]
    package_sha256: str = ""
    manifest_sha256: str = ""
    rendered_page_count: int | None = None
    tool_versions: dict[str, str] = field(default_factory=dict)
    execution: dict = field(default_factory=dict)
    render_duration_ms: int | None = None

    def as_dict(self) -> dict:
        return {
            "valid": self.valid,
            "issues": [item.as_dict() for item in self.issues],
            "package_sha256": self.package_sha256,
            "manifest_sha256": self.manifest_sha256,
            "rendered_page_count": self.rendered_page_count,
            "tool_versions": self.tool_versions,
            "execution": self.execution,
            "render_duration_ms": self.render_duration_ms,
        }
