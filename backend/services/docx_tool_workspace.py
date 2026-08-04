"""Replayable document IR with optimistic revisions and atomic batches."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from backend.schemas.docx_tool_schema import DocxToolCall
from backend.services.docx_content_catalog import DocxContentCatalog


class WorkspaceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    revision: int
    before_hash: str
    after_hash: str


class DocxWorkspace:
    SCHEMA_VERSION = "docx-workspace-v1"

    def __init__(self, catalog: DocxContentCatalog, state: dict, results: Optional[dict] = None):
        self.catalog = catalog
        self._state = copy.deepcopy(state)
        self._results = copy.deepcopy(results or {})

    @classmethod
    def create(cls, catalog: DocxContentCatalog) -> "DocxWorkspace":
        return cls(catalog, {
            "schema_version": cls.SCHEMA_VERSION,
            "catalog_hash": catalog.sha256,
            "revision": 0,
            "created": False,
            "finalized": False,
            "theme": "academic_blue",
            "page_layout": {"page_size": "letter", "orientation": "portrait"},
            "header_footer": {},
            "blocks": [],
        })

    @property
    def revision(self) -> int:
        return self._state["revision"]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    @property
    def canonical_bytes(self) -> bytes:
        return _bytes(self._state)

    def to_dict(self) -> dict:
        return copy.deepcopy(self._state)

    @classmethod
    def from_dict(cls, catalog: DocxContentCatalog, state: dict) -> "DocxWorkspace":
        if state.get("catalog_hash") != catalog.sha256:
            raise WorkspaceError("catalog_hash_mismatch", "workspace catalog hash mismatch")
        workspace = cls(catalog, state)
        workspace.validate_structure(require_complete=bool(state.get("finalized")))
        return workspace

    def replay(self, operations: Iterable[DocxToolCall]) -> "DocxWorkspace":
        replayed = self.create(self.catalog)
        replayed.apply_batch(list(operations))
        return replayed

    def apply_batch(self, operations: list[DocxToolCall]) -> list[OperationResult]:
        clone = DocxWorkspace(self.catalog, self._state, self._results)
        results = [clone.apply(operation) for operation in operations]
        clone.validate_structure(require_complete=clone._state["finalized"])
        self._state = clone._state
        self._results = clone._results
        return results

    def apply(self, operation: DocxToolCall) -> OperationResult:
        previous = self._results.get(operation.operation_id)
        if previous is not None:
            return OperationResult(**previous)
        if operation.expected_workspace_revision != self.revision:
            raise WorkspaceError("stale_revision", "expected workspace revision is stale")
        revision_tools = {"move_block", "update_block_style", "remove_decorative_block", "add_callout", "add_page_break"}
        if self._state["finalized"] and operation.tool not in revision_tools:
            raise WorkspaceError("workspace_finalized", "finalized workspace is immutable")
        before_hash = self.sha256
        self._execute(operation)
        self._state["revision"] += 1
        self.validate_structure(require_complete=self._state["finalized"])
        result = OperationResult(operation.operation_id, self.revision, before_hash, self.sha256)
        self._results[operation.operation_id] = result.__dict__
        return result

    def _block(self, block_id: str) -> dict:
        for block in self._state["blocks"]:
            if block["id"] == block_id:
                return block
        raise WorkspaceError("unknown_block", f"unknown block: {block_id}")

    def _add_block(self, block: dict) -> None:
        if any(existing["id"] == block["id"] for existing in self._state["blocks"]):
            raise WorkspaceError("duplicate_block", f"duplicate block ID: {block['id']}")
        parent_id = block.get("parent_id")
        if parent_id is not None:
            self._block(parent_id)
        block["order"] = sum(1 for item in self._state["blocks"] if item.get("parent_id") == parent_id)
        self._state["blocks"].append(block)

    def _execute(self, call: DocxToolCall) -> None:
        tool = call.tool
        args = call.arguments.model_dump(exclude_none=True)
        if tool == "create_document":
            if self._state["created"]:
                raise WorkspaceError("document_exists", "document is already created")
            self._state["created"] = True
            return
        if tool == "set_theme":
            self._state["theme"] = args["theme"]
            return
        if tool == "set_page_layout":
            self._state["page_layout"].update(args)
            return
        if tool == "set_header_footer":
            self._state["header_footer"] = args
            return
        if tool == "finalize_document":
            self._state["finalized"] = True
            return
        if tool == "move_block":
            block = self._block(args["block_id"])
            parent = self._block(args["parent_id"])
            cursor = parent
            while cursor.get("parent_id") is not None:
                if cursor["parent_id"] == block["id"]:
                    raise WorkspaceError("block_cycle", "block move would create a cycle")
                cursor = self._block(cursor["parent_id"])
            if parent["id"] == block["id"]:
                raise WorkspaceError("block_cycle", "block cannot parent itself")
            block["parent_id"] = parent["id"]
            return
        if tool == "update_block_style":
            self._block(args["block_id"])["style"] = args["style"]
            return
        if tool == "remove_decorative_block":
            block = self._block(args["block_id"])
            if not block.get("decorative"):
                raise WorkspaceError("assessed_block_removal", "only decorative blocks may be removed")
            descendants = {block["id"]}
            changed = True
            while changed:
                changed = False
                for item in self._state["blocks"]:
                    if item.get("parent_id") in descendants and item["id"] not in descendants:
                        descendants.add(item["id"]); changed = True
            if any(not item.get("decorative") for item in self._state["blocks"] if item["id"] in descendants):
                raise WorkspaceError("assessed_block_removal", "decorative parent contains assessed content")
            self._state["blocks"] = [item for item in self._state["blocks"] if item["id"] not in descendants]
            return

        block_type = {
            "add_section": "section", "add_heading": "heading", "add_content": "content",
            "add_question": "question", "add_equation": "equation", "add_solution": "solution",
            "add_answer_key": "answer_key", "add_quality_check": "quality_check",
            "add_callout": "callout", "add_table": "table", "add_page_break": "page_break",
        }.get(tool)
        if block_type is None:
            raise WorkspaceError("unsupported_tool", f"unsupported tool: {tool}")
        block_id = args.pop("block_id", call.operation_id + "-block")
        parent_id = args.pop("parent_id", None)
        decorative = (
            "literal_text" in args
            or (tool in {"add_heading", "add_callout"} and "content_ref" not in args)
        )
        if tool in {"add_content", "add_question", "add_solution", "add_equation"}:
            decorative = False
        if "content_ref" in args:
            self.catalog.resolve_text(args["content_ref"])
        if "question_id" in args:
            self.catalog.resolve_question(args["question_id"])
        if tool == "add_equation":
            self.catalog.resolve_equation(args["question_id"], args["equation_id"])
        self._add_block({"id": block_id, "type": block_type, "parent_id": parent_id, "decorative": decorative, **args})

    def validate_structure(self, *, require_complete: bool = False) -> None:
        ids = [block["id"] for block in self._state["blocks"]]
        if len(ids) != len(set(ids)):
            raise WorkspaceError("duplicate_block", "block IDs must be unique")
        valid_ids = set(ids)
        for block in self._state["blocks"]:
            if block.get("parent_id") is not None and block["parent_id"] not in valid_ids:
                raise WorkspaceError("unknown_parent", "block parent does not exist")
        if require_complete:
            for qid in self.catalog.question_ids:
                questions = [b for b in self._state["blocks"] if b["type"] == "question" and str(b.get("question_id")) == qid]
                solutions = [b for b in self._state["blocks"] if b["type"] == "solution" and str(b.get("question_id")) == qid]
                if len(questions) != 1 or len(solutions) != 1:
                    raise WorkspaceError("incomplete_assessment", f"question and solution {qid} must appear exactly once")
