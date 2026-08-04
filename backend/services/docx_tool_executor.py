"""Transactional executor facade for validated DOCX tool calls."""

from dataclasses import dataclass

from backend.schemas.docx_tool_schema import DocxToolCall
from backend.services.docx_tool_workspace import DocxWorkspace, OperationResult


@dataclass(frozen=True)
class BatchExecutionResult:
    workspace_revision: int
    workspace_hash: str
    actions: tuple[OperationResult, ...]


class DocxToolExecutor:
    def execute(self, workspace: DocxWorkspace, operations: list[DocxToolCall]) -> BatchExecutionResult:
        actions = workspace.apply_batch(operations)
        return BatchExecutionResult(workspace.revision, workspace.sha256, tuple(actions))
