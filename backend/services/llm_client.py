import json
import re
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types

from backend.config import settings


@dataclass(frozen=True)
class LLMResult:
    raw_text: str
    provider_request_id: Optional[str]
    model_name: str
    model_version: Optional[str]
    finish_reason: Optional[str]


class LLMClient:
    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.llm_model
        self._client = genai.Client(api_key=settings.google_api_key)

    def generate(self, system_prompt: str, user_message: str, model_settings: Optional[dict] = None) -> LLMResult:
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
        return LLMResult(
            raw_text=response.text,
            provider_request_id=getattr(response, "response_id", None),
            model_name=self.model,
            model_version=getattr(response, "model_version", None),
            finish_reason=finish_reason,
        )

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
