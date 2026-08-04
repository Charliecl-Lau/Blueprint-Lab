from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import ValidationError

from backend.schemas.docx_authoring_schema import DocxProgramEnvelope
from backend.services.docx_authoring_provider import AuthoringResult, RepairContext
from backend.services.docx_grounding import DocxGrounding
from backend.services.llm_client import LLMClient
from backend.services.reproducibility import canonical_json, sha256_text


DOCX_AUTHORING_MODEL = "gemini-3.5-flash-lite"
_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


class AuthoringEnvelopeError(ValueError):
    pass


class GeminiDocxAuthoringProvider:
    def __init__(self, client: LLMClient | None = None):
        self.client = client or LLMClient(model=DOCX_AUTHORING_MODEL)
        if self.client.model != DOCX_AUTHORING_MODEL:
            raise ValueError(f"DOCX authoring requires {DOCX_AUTHORING_MODEL}")

    def author_program(
        self,
        grounding: DocxGrounding,
        *,
        attempt_number: int,
        repair_context: RepairContext | None = None,
    ) -> AuthoringResult:
        if attempt_number not in (1, 2):
            raise ValueError("DOCX authoring permits attempts 1 and 2 only")
        if (attempt_number == 2) != (repair_context is not None):
            raise ValueError("repair context is required only for attempt 2")
        system_prompt = (_PROMPTS / "docx_authoring_system.md").read_text(encoding="utf-8")
        user_message = grounding.provider_message()
        if repair_context is not None:
            system_prompt += "\n\n" + (_PROMPTS / "docx_authoring_repair.md").read_text(encoding="utf-8")
            repair_payload = {
                "previous_program": repair_context.previous_program,
                "issues": repair_context.issues,
                "stdout": repair_context.stdout[-8192:],
                "stderr": repair_context.stderr[-8192:],
            }
            user_message += "\nREPAIR_CONTEXT_JSON\n" + canonical_json(repair_payload)
        prompt_hash = sha256_text(system_prompt + "\n" + user_message)
        started = time.perf_counter()
        result = self.client.generate(
            system_prompt=system_prompt,
            user_message=user_message,
            model_settings={"max_output_tokens": 65536},
            response_schema=DocxProgramEnvelope,
            attachments=grounding.attachments,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        raw = result.raw_text.strip()
        if raw.startswith("```") or not raw.startswith("{") or not raw.endswith("}"):
            raise AuthoringEnvelopeError("provider returned prose or Markdown instead of one JSON envelope")
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise TypeError("envelope must be an object")
            envelope = DocxProgramEnvelope.model_validate(parsed)
        except (json.JSONDecodeError, TypeError, ValidationError) as exc:
            raise AuthoringEnvelopeError("provider returned an invalid DOCX program envelope") from exc
        if envelope.grounding_sha256 != grounding.sha256:
            raise AuthoringEnvelopeError("provider envelope grounding hash mismatch")
        return AuthoringResult(
            envelope=envelope,
            provider_result=result,
            duration_ms=duration_ms,
            prompt_sha256=prompt_hash,
        )
