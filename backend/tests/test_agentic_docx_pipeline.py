from types import SimpleNamespace

from backend.schemas.docx_tool_schema import DocxDesignTurn, DocxReviewTurn
from backend.services.agentic_docx_pipeline import AgenticDocxPipeline
from backend.services.agentic_docx_compiler import AgenticDocxCompiler
from backend.services.docx_visual_renderer import PageImage, VisualFinding


ASSESSMENT = {"questions": [{
    "type": "short_answer", "id": "1", "metadata": {"question_title": "Q"},
    "body": "Body", "options": [], "model_answer": "Answer", "equations": [],
    "revision_options": ["A", "B"],
}]}


class FakeAgent:
    def __init__(self, reviews): self.reviews = iter(reviews)
    def design(self, catalog, workspace, required_sections):
        operations = []
        for index, (tool, arguments) in enumerate([
            ("create_document", {}),
            ("add_section", {"block_id": "questions", "role": "questions"}),
            ("add_question", {"block_id": "q1", "parent_id": "questions", "question_id": "1"}),
            ("add_section", {"block_id": "solutions", "role": "solutions"}),
            ("add_solution", {"block_id": "s1", "parent_id": "solutions", "question_id": "1"}),
            ("finalize_document", {}),
        ]):
            operations.append({"operation_id": f"d-{index}", "tool": tool, "expected_workspace_revision": index, "arguments": arguments})
        return SimpleNamespace(turn=DocxDesignTurn(rationale="test", operations=operations))
    def review(self, *args, **kwargs): return SimpleNamespace(turn=next(self.reviews))


class FakeRender:
    def __init__(self, fatal=False): self.fatal = fatal
    def render(self, value):
        page = PageImage(1, 100, 100, 3, "0" * 64, "opaque", b"png")
        finding = [VisualFinding("fatal", "error", 1, "bad")] if self.fatal else []
        return SimpleNamespace(pages=(page,), findings=tuple(finding), close=lambda: None)


def test_pipeline_approves_first_render():
    pipeline = AgenticDocxPipeline(agent=FakeAgent([DocxReviewTurn(decision="approve")]), renderer=FakeRender(), compiler=AgenticDocxCompiler())
    result = pipeline.run(ASSESSMENT)
    assert result.succeeded and result.decision == "approve" and result.evidence.render_count == 1


def test_machine_fatal_cannot_be_approved():
    pipeline = AgenticDocxPipeline(agent=FakeAgent([DocxReviewTurn(decision="approve")]), renderer=FakeRender(fatal=True), compiler=AgenticDocxCompiler())
    result = pipeline.run(ASSESSMENT)
    assert not result.succeeded and result.decision == "machine_failed"


def test_one_targeted_revision_then_approval():
    revision = DocxReviewTurn(decision="revise", operations=[{
        "operation_id": "r-1", "tool": "update_block_style",
        "expected_workspace_revision": 6,
        "arguments": {"block_id": "q1", "style": "numbered_card"},
    }])
    pipeline = AgenticDocxPipeline(agent=FakeAgent([revision, DocxReviewTurn(decision="approve")]), renderer=FakeRender(), compiler=AgenticDocxCompiler())
    result = pipeline.run(ASSESSMENT)
    assert result.succeeded and result.evidence.render_count == 2
    assert result.evidence.workspace_revision == 7


def test_revision_budget_exhaustion_preserves_failure_result():
    revision = DocxReviewTurn(decision="revise", operations=[{
        "operation_id": "r-1", "tool": "update_block_style",
        "expected_workspace_revision": 6,
        "arguments": {"block_id": "q1", "style": "numbered_card"},
    }])
    pipeline = AgenticDocxPipeline(agent=FakeAgent([revision]), renderer=FakeRender(), compiler=AgenticDocxCompiler(), maximum_revisions=0)
    result = pipeline.run(ASSESSMENT)
    assert not result.succeeded and result.decision == "budget_exhausted"
    assert result.evidence.workspace_revision == 6


def test_stale_revision_batch_fails_without_workspace_mutation():
    revision = DocxReviewTurn(decision="revise", operations=[{
        "operation_id": "r-1", "tool": "update_block_style",
        "expected_workspace_revision": 5,
        "arguments": {"block_id": "q1", "style": "numbered_card"},
    }])
    pipeline = AgenticDocxPipeline(agent=FakeAgent([revision]), renderer=FakeRender(), compiler=AgenticDocxCompiler())
    result = pipeline.run(ASSESSMENT)
    assert not result.succeeded and result.safe_issue_codes == ("stale_revision",)
    assert result.evidence.workspace_revision == 6
