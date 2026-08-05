"""Manual, bounded Luna turns for selecting trusted DOCX tools."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Type

from pydantic import BaseModel, ValidationError

from backend.config import settings
from backend.schemas.docx_tool_schema import DocxDesignTurn, DocxReviewTurn
from backend.services.docx_content_catalog import DocxContentCatalog
from backend.services.docx_tool_workspace import DocxWorkspace
from backend.services.llm_client import LLMClient, LLMResult


PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
DOCX_TOOL_MODEL = "gpt-5.6-luna"
REVIEW_REVISION_TOOLS = {
    "move_block",
    "update_block_style",
    "remove_decorative_block",
    "add_callout",
    "add_page_break",
}


class DocxToolAgentError(ValueError): pass


@dataclass(frozen=True)
class AgentTurnResult:
    turn: BaseModel
    provider_result: LLMResult
    duration_ms: int
    prompt_sha256: str


class GeminiDocxToolAgent:
    def __init__(self, client: Optional[LLMClient] = None, *, max_operations: int = 100, max_pages: int = 25):
        self.client = client or LLMClient(
            provider="openai",
            model=DOCX_TOOL_MODEL,
            timeout_ms=settings.docx_tool_provider_timeout_seconds * 1000,
        )
        if self.client.model != DOCX_TOOL_MODEL:
            raise ValueError(f"agentic DOCX requires {DOCX_TOOL_MODEL}")
        self.max_operations = max_operations; self.max_pages = max_pages

    def design(self, catalog: DocxContentCatalog, workspace: DocxWorkspace, *, required_sections: list[str]) -> AgentTurnResult:
        context = {"catalog": catalog.provider_index(), "required_sections": required_sections, "workspace": workspace.to_dict(), "limits": {"maximum_operations": self.max_operations}}
        return self._structured_turn(
            "docx_tool_design_system.md",
            context,
            DocxDesignTurn,
            normalizer=lambda value: self._normalize_design_turn(
                value, catalog, workspace.revision
            ),
        )

    def review(self, catalog: DocxContentCatalog, workspace: DocxWorkspace, rendered, *, validator_findings: list[dict], previous_decisions: list[str]) -> AgentTurnResult:
        pages = list(rendered.pages[:self.max_pages])
        context = {
            "catalog_sha256": catalog.sha256,
            "workspace": workspace.to_dict(),
            "machine_findings": validator_findings,
            "previous_decisions": previous_decisions,
            "page_metadata": [page.public_metadata() for page in pages],
            "limits": {"maximum_operations": self.max_operations, "maximum_pages": self.max_pages},
        }
        return self._structured_turn(
            "docx_tool_visual_review.md",
            context,
            DocxReviewTurn,
            images=[page.inline_part() for page in pages],
            normalizer=lambda value: self._normalize_review_turn(
                value, workspace.revision
            ),
        )

    def _structured_turn(self, prompt_name: str, context: dict, schema: Type[BaseModel], images=None, normalizer=None) -> AgentTurnResult:
        system = (PROMPTS / prompt_name).read_text(encoding="utf-8")
        message = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        prompt_hash = hashlib.sha256((system + "\n" + message).encode()).hexdigest()
        started = time.perf_counter()
        if images:
            result = self.client.generate_multimodal(system, message, images, response_schema=schema, model_settings={"max_output_tokens": 32768})
        else:
            result = self.client.generate(system, message, model_settings={"max_output_tokens": 32768}, response_schema=schema)
        duration_ms = int((time.perf_counter() - started) * 1000)
        raw = result.raw_text.strip()
        if not raw.startswith("{") or not raw.endswith("}"):
            raise DocxToolAgentError("provider returned prose, code, or Markdown")
        try:
            parsed = json.loads(raw)
            if normalizer is not None:
                parsed = normalizer(parsed)
            turn = schema.model_validate(parsed)
        except ValidationError as exc:
            safe_errors = []
            for error in exc.errors(include_url=False)[:10]:
                location = ".".join(str(part) for part in error["loc"])
                message = str(error.get("msg", "invalid")).replace(",", ";")[:120]
                safe_errors.append(f"{location}:{error.get('type', 'invalid')}:{message}")
            suffix = "|".join(safe_errors) or "root"
            raise DocxToolAgentError(
                f"provider returned an invalid tool turn at {suffix}"
            ) from exc
        except (json.JSONDecodeError, TypeError) as exc:
            raise DocxToolAgentError("provider returned malformed tool JSON") from exc
        if len(turn.operations) > self.max_operations:
            raise DocxToolAgentError("provider operation batch exceeds limit")
        return AgentTurnResult(turn, result, duration_ms, prompt_hash)

    @staticmethod
    def _normalize_design_turn(value: dict, catalog: DocxContentCatalog, base_revision: int) -> dict:
        """Fill catalog-derived identifiers omitted by the provider's flat schema.

        No assessed strings are introduced here. Empty content operations are
        discarded because they resolve no immutable catalog entry.
        """
        if not isinstance(value, dict) or not isinstance(value.get("operations"), list):
            return value
        question_ids = list(catalog.question_ids)
        question_cursor = 0
        solution_cursor = 0
        normalized = []
        seen_operation_ids = set()
        for source in value["operations"]:
            if not isinstance(source, dict):
                normalized.append(source)
                continue
            operation = dict(source)
            arguments = dict(operation.get("arguments") or {})
            tool = operation.get("tool")
            if tool == "add_content" and not arguments.get("content_ref"):
                continue
            if tool == "add_equation":
                # The compiler resolves and places the immutable equation
                # registry by question and location; provider pairings are
                # advisory and cannot override that mapping.
                continue
            if tool == "add_question":
                if not arguments.get("question_id") and question_cursor < len(question_ids):
                    arguments["question_id"] = question_ids[question_cursor]
                question_cursor += 1
            elif tool == "add_solution":
                if not arguments.get("question_id") and solution_cursor < len(question_ids):
                    arguments["question_id"] = question_ids[solution_cursor]
                solution_cursor += 1
            operation_id = operation.get("operation_id")
            if not isinstance(operation_id, str) or not operation_id or operation_id in seen_operation_ids:
                operation_id = f"design-op-{len(normalized) + 1:03d}"
            seen_operation_ids.add(operation_id)
            operation["operation_id"] = operation_id
            operation["expected_workspace_revision"] = base_revision + len(normalized)
            operation["arguments"] = arguments
            normalized.append(operation)
        return {**value, "operations": normalized}

    @staticmethod
    def _normalize_review_turn(value: dict, base_revision: int) -> dict:
        if not isinstance(value, dict) or not isinstance(value.get("operations"), list):
            return value
        normalized = []
        seen_operation_ids = set()
        for source in value["operations"]:
            if not isinstance(source, dict):
                normalized.append(source)
                continue
            operation = dict(source)
            if operation.get("tool") not in REVIEW_REVISION_TOOLS:
                # The design compiler owns assessed structure and equation
                # placement. A visual review may only request mutations that
                # the finalized workspace explicitly permits.
                continue
            operation_id = operation.get("operation_id")
            if not isinstance(operation_id, str) or not operation_id or operation_id in seen_operation_ids:
                operation_id = f"review-op-{len(normalized) + 1:03d}"
            seen_operation_ids.add(operation_id)
            operation["operation_id"] = operation_id
            operation["expected_workspace_revision"] = base_revision + len(normalized)
            operation["arguments"] = dict(operation.get("arguments") or {})
            normalized.append(operation)
        decision = value.get("decision")
        if decision == "revise" and not normalized:
            decision = "reject"
        return {**value, "decision": decision, "operations": normalized}
