"""Authoritative combination of machine validation and Gemini visual advice."""

from dataclasses import dataclass

from backend.schemas.docx_tool_schema import DocxReviewTurn


@dataclass(frozen=True)
class VisualReviewOutcome:
    decision: str
    safe_issue_codes: tuple[str, ...]


def resolve_visual_review(review: DocxReviewTurn, machine_findings) -> VisualReviewOutcome:
    fatal = tuple(item.code for item in machine_findings if item.severity == "error")
    if fatal:
        return VisualReviewOutcome("machine_failed", fatal)
    return VisualReviewOutcome(review.decision, tuple())
