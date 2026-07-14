import asyncio
import json
import re
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types

from backend.config import settings


def _without_defaults(value):
    if isinstance(value, dict):
        return {
            key: _without_defaults(item)
            for key, item in value.items()
            if key != "default"
        }
    if isinstance(value, list):
        return [_without_defaults(item) for item in value]
    return value


class TruncatedResponseError(RuntimeError):
    """Raised when the provider stopped before completing the response.

    Thinking tokens can be charged against max_output_tokens. When the
    combined thinking and output exceeds the budget, the provider can return
    truncated, unparseable JSON. The partial result retains provider usage so
    callers can account for the completed request before retrying.
    """

    def __init__(self, result: "LLMResult"):
        self.result = result
        super().__init__(
            "Provider stopped with finish_reason=MAX_TOKENS; response is "
            f"truncated and cannot be parsed. Model={result.model_name}."
        )


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int]
    cached_content_tokens: Optional[int]
    reasoning_tokens: Optional[int]
    extra_token_counts: dict[str, int]


@dataclass(frozen=True)
class LLMResult:
    raw_text: str
    provider_request_id: Optional[str]
    model_name: str
    model_version: Optional[str]
    finish_reason: Optional[str]
    usage: Optional[TokenUsage] = None


def _usage_from_response(response) -> Optional[TokenUsage]:
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return None
    raw = (
        metadata.model_dump(exclude_none=True)
        if hasattr(metadata, "model_dump")
        else vars(metadata)
    )
    known = {
        "prompt_token_count",
        "candidates_token_count",
        "total_token_count",
        "cached_content_token_count",
        "thoughts_token_count",
    }
    extras = {
        key: value
        for key, value in raw.items()
        if key.endswith("_token_count")
        and key not in known
        and isinstance(value, int)
    }
    return TokenUsage(
        input_tokens=getattr(metadata, "prompt_token_count", None),
        output_tokens=getattr(metadata, "candidates_token_count", None),
        total_tokens=getattr(metadata, "total_token_count", None),
        cached_content_tokens=getattr(metadata, "cached_content_token_count", None),
        reasoning_tokens=getattr(metadata, "thoughts_token_count", None),
        extra_token_counts=extras,
    )


class LLMClient:
    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.llm_model
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        self._client = genai.Client(api_key=settings.google_api_key)

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        model_settings: Optional[dict] = None,
        response_schema: Optional[type] = None,
    ) -> LLMResult:
        overrides = model_settings or {}
        config_kwargs = {
            "system_instruction": system_prompt,
            "temperature": overrides.get("temperature", settings.llm_temperature),
            "top_p": overrides.get("top_p", settings.llm_top_p),
            "max_output_tokens": overrides.get("max_tokens", settings.llm_max_output_tokens),
        }
        seed = overrides.get("seed", settings.llm_seed)
        if seed is not None:
            config_kwargs["seed"] = seed
        if response_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            schema = (
                response_schema.model_json_schema()
                if hasattr(response_schema, "model_json_schema")
                else response_schema
            )
            config_kwargs["response_schema"] = _without_defaults(schema)
        response = self._client.models.generate_content(
            model=self.model,
            config=types.GenerateContentConfig(**config_kwargs),
            contents=user_message,
        )
        finish_reason = None
        candidates = getattr(response, "candidates", None)
        if candidates:
            finish_reason = getattr(candidates[0], "finish_reason", None)
            finish_reason = getattr(finish_reason, "value", finish_reason)
        result = LLMResult(
            raw_text=response.text,
            provider_request_id=getattr(response, "response_id", None),
            model_name=self.model,
            model_version=getattr(response, "model_version", None),
            finish_reason=finish_reason,
            usage=_usage_from_response(response),
        )
        if finish_reason in ("MAX_TOKENS", 2):
            raise TruncatedResponseError(result)
        return result

    def generate_json(self, system_prompt: str, user_message: str) -> dict:
        result = self.generate(system_prompt, user_message)
        return _parse_json(result.raw_text)


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if match:
        return json.loads(match.group(1))
    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        return json.loads(match.group(1))
    raise ValueError(f"Could not parse JSON from LLM response. First 300 chars: {text[:300]}")
