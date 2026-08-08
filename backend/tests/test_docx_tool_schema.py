import pytest
from pydantic import ValidationError
from unittest.mock import patch

from backend.schemas.docx_tool_schema import DocxDesignTurn, DocxReviewTurn, DocxToolCall
from backend.services.docx_content_catalog import DocxContentCatalog
from backend.services.gemini_docx_tool_agent import DOCX_TOOL_MODEL, GeminiDocxToolAgent


def test_agentic_docx_client_uses_extended_provider_timeout():
    with patch(
        "backend.services.gemini_docx_tool_agent.LLMClient"
    ) as client_class:
        client_class.return_value.model = DOCX_TOOL_MODEL

        GeminiDocxToolAgent()

    client_class.assert_called_once_with(
        provider="google",
        model=DOCX_TOOL_MODEL,
        timeout_ms=300_000,
    )


def test_valid_equation_call_uses_registry_ids():
    call = DocxToolCall.model_validate({
        "operation_id": "design-1-op-004",
        "tool": "add_equation",
        "expected_workspace_revision": 3,
        "arguments": {"block_id": "q20-eq", "parent_id": "question-20", "question_id": "20", "equation_id": "alpha", "alignment": "center"},
    })
    assert call.tool == "add_equation"


def test_block_ids_are_deterministically_supplied_and_root_parent_is_valid():
    call = DocxToolCall.model_validate({
        "operation_id": "design-1-op-004",
        "tool": "add_content",
        "expected_workspace_revision": 3,
        "arguments": {"content_ref": "question.20.body"},
    })
    assert call.arguments.block_id == "design-1-op-004-block"
    assert call.arguments.parent_id is None


@pytest.mark.parametrize("bad", [
    {"operation_id": "x", "tool": "run_code", "expected_workspace_revision": 0, "arguments": {}},
    {"operation_id": "x", "tool": "add_equation", "expected_workspace_revision": 0, "arguments": {"raw_xml": "<m:oMath/>"}},
    {"operation_id": "x", "tool": "create_document", "expected_workspace_revision": 0, "arguments": {"path": "C:/secret"}},
    {"operation_id": "x", "tool": "set_theme", "expected_workspace_revision": 0, "arguments": {"theme": "unknown"}},
])
def test_protocol_rejects_untrusted_capabilities(bad):
    with pytest.raises(ValidationError):
        DocxToolCall.model_validate(bad)


def test_review_decision_contract():
    with pytest.raises(ValidationError):
        DocxReviewTurn(decision="approve", observations=[], operations=[{
            "operation_id": "x", "tool": "finalize_document", "expected_workspace_revision": 0, "arguments": {}
        }])
    with pytest.raises(ValidationError):
        DocxReviewTurn(decision="revise", observations=[], operations=[])
    assert DocxDesignTurn(rationale="Clear hierarchy", operations=[]).rationale


def test_design_normalization_uses_only_catalog_ids_and_reindexes_revisions():
    catalog = DocxContentCatalog.from_assessment({"questions": [{
        "id": "7", "type": "short_answer", "metadata": {"question_title": "Q"},
        "body": "Body", "options": [], "model_answer": "Answer",
        "equations": [], "revision_options": ["A", "B"],
    }]})
    normalized = GeminiDocxToolAgent._normalize_design_turn({
        "rationale": "test",
        "operations": [
            {"operation_id": "one", "tool": "create_document", "expected_workspace_revision": 9, "arguments": {}},
            {"operation_id": "empty", "tool": "add_content", "expected_workspace_revision": 10, "arguments": {}},
            {"operation_id": "question", "tool": "add_question", "expected_workspace_revision": 11, "arguments": {}},
            {"operation_id": "equation", "tool": "add_equation", "expected_workspace_revision": 12, "arguments": {"question_id": "7", "equation_id": "unsafe-provider-pair"}},
            {"operation_id": "solution", "tool": "add_solution", "expected_workspace_revision": 13, "arguments": {}},
        ],
    }, catalog, 0)
    assert [item["expected_workspace_revision"] for item in normalized["operations"]] == [0, 1, 2]
    assert normalized["operations"][1]["arguments"]["question_id"] == "7"
    assert normalized["operations"][2]["arguments"]["question_id"] == "7"


def test_review_normalization_owns_optimistic_revisions():
    normalized = GeminiDocxToolAgent._normalize_review_turn({
        "decision": "revise", "observations": [],
        "operations": [
            {"operation_id": "one", "tool": "update_block_style", "expected_workspace_revision": 0, "arguments": {"block_id": "q", "style": "compact"}},
            {"operation_id": "two", "tool": "move_block", "expected_workspace_revision": 0, "arguments": {"block_id": "q", "parent_id": "section"}},
        ],
    }, 40)
    assert [item["expected_workspace_revision"] for item in normalized["operations"]] == [40, 41]


def test_review_normalization_discards_application_owned_equation_operations():
    normalized = GeminiDocxToolAgent._normalize_review_turn({
        "decision": "revise",
        "observations": [{"page": 1, "code": "equation_layout", "message": "Adjust equations."}],
        "operations": [
            {"operation_id": "equation-1", "tool": "add_equation", "expected_workspace_revision": 3, "arguments": {"question_id": "7"}},
            {"operation_id": "equation-2", "tool": "add_equation", "expected_workspace_revision": 4, "arguments": {"question_id": "7"}},
        ],
    }, 40)

    assert normalized["operations"] == []
    assert normalized["decision"] == "reject"
    assert DocxReviewTurn.model_validate(normalized).decision == "reject"


def test_review_normalization_keeps_only_finalized_workspace_revision_tools():
    normalized = GeminiDocxToolAgent._normalize_review_turn({
        "decision": "revise",
        "observations": [],
        "operations": [
            {"operation_id": "heading", "tool": "add_heading", "expected_workspace_revision": 1, "arguments": {"literal_text": "Extra"}},
            {"operation_id": "style", "tool": "update_block_style", "expected_workspace_revision": 1, "arguments": {"block_id": "question-7", "style": "compact"}},
        ],
    }, 12)

    assert [item["tool"] for item in normalized["operations"]] == ["update_block_style"]
    assert normalized["operations"][0]["expected_workspace_revision"] == 12
    assert normalized["decision"] == "revise"
