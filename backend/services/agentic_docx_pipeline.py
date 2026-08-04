"""Bounded application-owned design, compile, render, and review loop."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from backend.services.agentic_docx_compiler import AgenticDocxCompiler, CompiledAgenticDocx
from backend.services.docx_content_catalog import DocxContentCatalog
from backend.services.docx_tool_executor import DocxToolExecutor
from backend.services.docx_tool_workspace import DocxWorkspace
from backend.services.docx_tool_workspace import WorkspaceError
from backend.services.docx_visual_renderer import DocxVisualRenderer
from backend.services.docx_visual_review import resolve_visual_review
from backend.services.gemini_docx_tool_agent import GeminiDocxToolAgent


REQUIRED_SECTIONS = ["assessment_metadata", "questions", "solutions", "answer_key", "quality_check", "revision_options"]


@dataclass(frozen=True)
class AgenticPipelineEvidence:
    workspace_hash: str
    workspace_revision: int
    render_count: int
    page_images: tuple[dict, ...]
    review_decisions: tuple[str, ...]
    tool_names: tuple[str, ...]


@dataclass(frozen=True)
class AgenticPipelineResult:
    succeeded: bool
    decision: str
    compiled: Optional[CompiledAgenticDocx]
    evidence: AgenticPipelineEvidence
    safe_issue_codes: tuple[str, ...] = ()


class AgenticDocxPipeline:
    def __init__(self, *, agent: Optional[GeminiDocxToolAgent] = None, executor: Optional[DocxToolExecutor] = None, compiler: Optional[AgenticDocxCompiler] = None, renderer: Optional[DocxVisualRenderer] = None, maximum_revisions: int = 2, maximum_total_seconds: int = 180, progress: Optional[Callable[[str], None]] = None, model_turn: Optional[Callable[[str, int, object], None]] = None, action_batch: Optional[Callable[[int, str, list, object], None]] = None, rendered_draft: Optional[Callable[[int, object, object], None]] = None):
        self.agent = agent or GeminiDocxToolAgent(); self.executor = executor or DocxToolExecutor()
        self.compiler = compiler or AgenticDocxCompiler(); self.renderer = renderer or DocxVisualRenderer()
        self.maximum_revisions = maximum_revisions; self.maximum_total_seconds = maximum_total_seconds
        self.progress = progress or (lambda _: None); self.model_turn = model_turn or (lambda *_: None)
        self.action_batch = action_batch or (lambda *_: None)
        self.rendered_draft = rendered_draft or (lambda *_: None)

    def run(self, assessment_json: dict, *, session_id: Optional[int] = None) -> AgenticPipelineResult:
        started = time.monotonic(); catalog = DocxContentCatalog.from_assessment(assessment_json); workspace = DocxWorkspace.create(catalog)
        tool_names = []; decisions = []; page_evidence = []; render_count = 0; compiled = None
        self.progress("docx_authoring")
        design = self.agent.design(catalog, workspace, required_sections=REQUIRED_SECTIONS)
        self.model_turn("docx_tool_design", 1, design)
        self.progress("docx_executing")
        try:
            executed = self.executor.execute(workspace, design.turn.operations)
        except WorkspaceError as exc:
            return self._result(False, "machine_failed", None, workspace, render_count, page_evidence, decisions, tool_names, (exc.code,))
        self.action_batch(0, "design", design.turn.operations, executed)
        tool_names.extend(call.tool for call in design.turn.operations)

        for review_number in range(1, self.maximum_revisions + 2):
            if time.monotonic() - started > self.maximum_total_seconds:
                return self._result(False, "budget_exhausted", None, workspace, render_count, page_evidence, decisions, tool_names, ("wall_time_budget",))
            self.progress("docx_validating")
            compiled = self.compiler.compile(workspace, session_id=session_id, iteration_number=review_number - 1)
            rendered = self.renderer.render(compiled.docx_bytes); render_count += 1
            try:
                self.rendered_draft(review_number - 1, compiled, rendered)
                metadata = [page.public_metadata() for page in rendered.pages]; page_evidence.extend(metadata)
                findings = [finding.__dict__ for finding in rendered.findings]
                self.progress("docx_repairing" if review_number > 1 else "docx_validating")
                review = self.agent.review(catalog, workspace, rendered, validator_findings=findings, previous_decisions=decisions)
                self.model_turn("docx_visual_review", review_number, review)
                outcome = resolve_visual_review(review.turn, rendered.findings); decisions.append(review.turn.decision)
            finally:
                rendered.close()
            if outcome.decision == "machine_failed":
                return self._result(False, outcome.decision, None, workspace, render_count, page_evidence, decisions, tool_names, outcome.safe_issue_codes)
            if outcome.decision == "approve":
                return self._result(True, "approve", compiled, workspace, render_count, page_evidence, decisions, tool_names)
            if outcome.decision == "reject":
                return self._result(False, "reject", None, workspace, render_count, page_evidence, decisions, tool_names, ("visual_review_rejected",))
            if review_number > self.maximum_revisions:
                return self._result(False, "budget_exhausted", None, workspace, render_count, page_evidence, decisions, tool_names, ("revision_budget_exhausted",))
            self.progress("docx_repairing")
            try:
                executed = self.executor.execute(workspace, review.turn.operations)
            except WorkspaceError as exc:
                return self._result(False, "machine_failed", None, workspace, render_count, page_evidence, decisions, tool_names, (exc.code,))
            self.action_batch(review_number, "visual_revision", review.turn.operations, executed)
            tool_names.extend(call.tool for call in review.turn.operations)
        raise AssertionError("bounded loop exhausted unexpectedly")

    @staticmethod
    def _result(succeeded, decision, compiled, workspace, render_count, pages, decisions, tools, issues=()):
        evidence = AgenticPipelineEvidence(workspace.sha256, workspace.revision, render_count, tuple(pages), tuple(decisions), tuple(tools))
        return AgenticPipelineResult(succeeded, decision, compiled, evidence, tuple(issues))
