import pytest

from backend.schemas.docx_tool_schema import DocxToolCall
from backend.services.docx_content_catalog import DocxContentCatalog
from backend.services.docx_tool_workspace import DocxWorkspace, WorkspaceError


def _catalog():
    return DocxContentCatalog.from_assessment({"questions": [{
        "type": "short_answer", "id": "1", "metadata": {"question_title": "Q"},
        "body": "Body", "options": [], "model_answer": "Answer", "equations": [],
        "revision_options": ["A", "B"],
    }]})


def _call(op, tool, rev, **arguments):
    return DocxToolCall(operation_id=op, tool=tool, expected_workspace_revision=rev, arguments=arguments)


def test_workspace_is_deterministic_idempotent_and_transactional():
    workspace = DocxWorkspace.create(_catalog())
    initial = workspace.sha256
    result = workspace.apply(_call("one", "create_document", 0))
    assert workspace.revision == 1 and result.after_hash == workspace.sha256
    assert workspace.apply(_call("one", "create_document", 0)) == result
    with pytest.raises(WorkspaceError):
        workspace.apply_batch([
            _call("two", "add_section", 1, block_id="questions", role="questions"),
            _call("three", "add_content", 2, block_id="bad", parent_id="missing", content_ref="question.1.body"),
        ])
    assert workspace.revision == 1
    assert initial != workspace.sha256


def test_stale_revision_and_cycles_do_not_mutate():
    workspace = DocxWorkspace.create(_catalog())
    workspace.apply(_call("one", "add_section", 0, block_id="a", role="questions"))
    with pytest.raises(WorkspaceError):
        workspace.apply(_call("stale", "add_section", 0, block_id="b", role="solutions"))
    workspace.apply(_call("two", "add_section", 1, block_id="b", parent_id="a", role="solutions"))
    with pytest.raises(WorkspaceError):
        workspace.apply(_call("cycle", "move_block", 2, block_id="a", parent_id="b"))
    assert workspace.revision == 2


def test_empty_model_heading_is_decorative_but_assessed_content_is_protected():
    workspace = DocxWorkspace.create(_catalog())
    workspace.apply(_call("heading", "add_heading", 0))
    workspace.apply(_call("remove-heading", "remove_decorative_block", 1, block_id="heading-block"))
    workspace.apply(_call("content", "add_content", 2, block_id="body", content_ref="question.1.body"))
    with pytest.raises(WorkspaceError, match="only decorative"):
        workspace.apply(_call("remove-body", "remove_decorative_block", 3, block_id="body"))
