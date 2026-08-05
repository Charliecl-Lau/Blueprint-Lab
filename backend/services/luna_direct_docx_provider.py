"""Generate a DOCX from canonical assessment JSON in an ephemeral OpenAI container."""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from openai import OpenAI

from backend.config import settings
from backend.services.llm_client import LLMResult, TokenUsage
from backend.services.reproducibility import canonical_json


LUNA_DIRECT_MODEL = "gpt-5.6-luna"
_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "luna_direct_docx_system.md"


class LunaDocxGenerationError(RuntimeError):
    """Safe failure raised when the direct DOCX contract is not satisfied."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LunaDocxResult:
    content: bytes
    provider_result: LLMResult
    container_id: str
    file_id: str
    filename: str
    prompt_sha256: str


def _value(item: Any, name: str, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _container_citations(value: Any) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, (str, bytes, bytearray)) or value is None:
        return found
    if _value(value, "type") == "container_file_citation":
        found.append(value)
        return found
    if isinstance(value, dict):
        children = value.values()
    elif isinstance(value, (list, tuple)):
        children = value
    elif hasattr(value, "model_dump"):
        children = value.model_dump(exclude_none=True).values()
    elif hasattr(value, "__dict__"):
        children = vars(value).values()
    else:
        return found
    for child in children:
        found.extend(_container_citations(child))
    return found


def _usage(response) -> TokenUsage | None:
    usage = _value(response, "usage")
    if usage is None:
        return None
    input_details = _value(usage, "input_tokens_details")
    output_details = _value(usage, "output_tokens_details")
    return TokenUsage(
        input_tokens=_value(usage, "input_tokens"),
        output_tokens=_value(usage, "output_tokens"),
        total_tokens=_value(usage, "total_tokens"),
        cached_content_tokens=_value(input_details, "cached_tokens"),
        reasoning_tokens=_value(output_details, "reasoning_tokens"),
        extra_token_counts={},
    )


def _download_bytes(download) -> bytes:
    if isinstance(download, bytes):
        return download
    read = getattr(download, "read", None)
    if callable(read):
        return read()
    content = getattr(download, "content", None)
    if isinstance(content, bytes):
        return content
    raise LunaDocxGenerationError("docx_download_invalid")


class LunaDirectDocxProvider:
    def __init__(self, client=None, *, maximum_bytes: int | None = None):
        self.client = client or OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.docx_tool_provider_timeout_seconds,
            # A repair is already the pipeline's bounded retry. Disable SDK-level
            # retries so one stalled HTTP request cannot silently multiply the
            # configured timeout and leave the run in docx_repairing for minutes.
            max_retries=0,
        )
        self.maximum_bytes = maximum_bytes or settings.docx_sandbox_max_response_bytes

    def generate(
        self,
        assessment_json: dict,
        *,
        run_id: int,
        verification_feedback: tuple[str, ...] = (),
    ) -> LunaDocxResult:
        instructions = _PROMPT_PATH.read_text(encoding="utf-8")
        if verification_feedback:
            findings = "\n".join(f"* {item}" for item in verification_feedback)
            instructions += (
                "\n\n# Machine Verification Repair\n\n"
                "A previous DOCX attempt failed the authoritative verifier. Rebuild "
                "the document from scratch and correct every finding below. Do not "
                "weaken, omit, or work around any validation requirement.\n\n"
                f"{findings}\n"
            )
        canonical = canonical_json(assessment_json)
        prompt_sha256 = hashlib.sha256(
            (instructions + "\n" + canonical).encode("utf-8")
        ).hexdigest()
        container = self.client.containers.create(
            name=f"blueprint-lab-run-{run_id}-docx",
            expires_after={"anchor": "last_active_at", "minutes": 20},
            extra_body={"memory_limit": "1g"},
        )
        container_id = _value(container, "id")
        if not container_id:
            raise LunaDocxGenerationError("container_creation_invalid")

        try:
            uploaded = self.client.containers.files.create(
                container_id,
                file=(
                    "assessment.json",
                    canonical.encode("utf-8"),
                    "application/json",
                ),
            )
            canonical_path = _value(uploaded, "path")
            if not canonical_path:
                raise LunaDocxGenerationError("canonical_file_upload_invalid")
            response = self.client.responses.create(
                model=LUNA_DIRECT_MODEL,
                instructions=instructions,
                input=[{
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": (
                            "The exact canonical JSON below is also mounted at "
                            f"{canonical_path}. Load that file directly; "
                            "do not retype its values into source code.\n\n"
                            f"{canonical}"
                        ),
                    }],
                }],
                tools=[{"type": "code_interpreter", "container": container_id}],
                tool_choice="required",
            )
            status = _value(response, "status")
            if status != "completed":
                raise LunaDocxGenerationError("docx_response_incomplete")
            citations = _container_citations(_value(response, "output", []))
            if len(citations) != 1:
                raise LunaDocxGenerationError("docx_citation_invalid")
            citation = citations[0]
            file_id = _value(citation, "file_id")
            filename = _value(citation, "filename", "")
            cited_container_id = _value(citation, "container_id")
            if (
                not file_id
                or cited_container_id != container_id
                or not filename.lower().endswith(".docx")
            ):
                raise LunaDocxGenerationError("docx_citation_invalid")
            download = self.client.containers.files.content.retrieve(
                file_id,
                container_id=container_id,
            )
            content = _download_bytes(download)
            if not content:
                raise LunaDocxGenerationError("docx_content_empty")
            if len(content) > self.maximum_bytes:
                raise LunaDocxGenerationError("docx_artifact_too_large")
            if not content.startswith(b"PK") or not zipfile.is_zipfile(BytesIO(content)):
                raise LunaDocxGenerationError("docx_package_invalid")
            provider_result = LLMResult(
                raw_text=_value(response, "output_text", "") or "",
                provider_request_id=_value(response, "id"),
                model_name=LUNA_DIRECT_MODEL,
                model_version=_value(response, "model"),
                finish_reason=status,
                usage=_usage(response),
            )
            return LunaDocxResult(
                content=content,
                provider_result=provider_result,
                container_id=container_id,
                file_id=file_id,
                filename=filename,
                prompt_sha256=prompt_sha256,
            )
        finally:
            try:
                self.client.containers.delete(container_id)
            except Exception:
                pass
