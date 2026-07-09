import json
import re
from typing import Optional

from google import genai
from google.genai import types

from backend.config import settings


class LLMClient:
    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.llm_model
        self._client = genai.Client(api_key=settings.google_api_key)

    def generate(self, system_prompt: str, user_message: str) -> str:
        response = self._client.models.generate_content(
            model=self.model,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
            contents=user_message,
        )
        return response.text

    def generate_json(self, system_prompt: str, user_message: str) -> dict:
        text = self.generate(system_prompt, user_message)
        return _parse_json(text)


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
