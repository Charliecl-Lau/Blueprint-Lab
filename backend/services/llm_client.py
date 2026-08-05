import asyncio
import base64
import json
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Optional, Sequence

from google import genai
from google.genai import errors as genai_errors, types
from openai import OpenAI
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from backend.config import settings
from backend.services.reference_pdfs import (
    ProviderFileAttachment,
    ValidatedReferencePdf,
)


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


def _gemini_response_schema(value):
    """Reduce JSON Schema to Gemini's supported structured-output subset.

    Application-side Pydantic validation remains authoritative for all bounds,
    extra-field rejection, and cross-field invariants.
    """
    if isinstance(value, dict):
        any_of = value.get("anyOf")
        if isinstance(any_of, list):
            non_null = [item for item in any_of if item.get("type") != "null"]
            if len(non_null) == 1:
                return _gemini_response_schema(non_null[0])
        unsupported = {
            "default",
            "title",
            "description",
            "additionalProperties",
            "maxLength",
            "minLength",
            "maxItems",
            "minItems",
            "minimum",
            "maximum",
        }
        return {
            key: _gemini_response_schema(item)
            for key, item in value.items()
            if key not in unsupported
        }
    if isinstance(value, list):
        return [_gemini_response_schema(item) for item in value]
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


def is_retryable_provider_error(exc: Exception) -> bool:
    """Return whether a provider request failed for a transient HTTP reason."""
    if isinstance(
        exc,
        (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError),
    ):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in {408, 409, 429} or exc.status_code >= 500
    if isinstance(exc, genai_errors.ServerError):
        return True
    return isinstance(exc, genai_errors.ClientError) and exc.code in {
        408,
        409,
        429,
    }


@dataclass(frozen=True)
class ModelCapabilities:
    supports_sampling_controls: bool


def capabilities_for(model: str) -> ModelCapabilities:
    if model.startswith("gemini-3"):
        return ModelCapabilities(supports_sampling_controls=False)
    return ModelCapabilities(supports_sampling_controls=True)


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


def _openai_usage_from_response(response) -> Optional[TokenUsage]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    input_details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    raw = usage.model_dump(exclude_none=True) if hasattr(usage, "model_dump") else {}
    known = {"input_tokens", "output_tokens", "total_tokens", "input_tokens_details", "output_tokens_details"}
    extras = {
        key: value
        for key, value in raw.items()
        if key not in known and key.endswith("_tokens") and isinstance(value, int)
    }
    return TokenUsage(
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
        cached_content_tokens=getattr(input_details, "cached_tokens", None),
        reasoning_tokens=getattr(output_details, "reasoning_tokens", None),
        extra_token_counts=extras,
    )


class LLMClient:
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        *,
        timeout_ms: int = 60_000,
    ):
        if timeout_ms <= 0:
            raise ValueError("provider timeout must be positive")
        self.provider = (provider or settings.llm_provider).lower()
        self.model = model or settings.llm_model
        if self.provider == "openai":
            self._client = OpenAI(
                api_key=settings.openai_api_key,
                timeout=timeout_ms / 1000,
            )
        elif self.provider == "google":
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())
            self._client = genai.Client(
                api_key=settings.google_api_key,
                http_options=types.HttpOptions(timeout=timeout_ms),
            )
        else:
            raise ValueError(f"unsupported LLM provider: {self.provider}")

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        model_settings: Optional[dict] = None,
        response_schema: Optional[type] = None,
        attachments: Sequence[ProviderFileAttachment] = (),
    ) -> LLMResult:
        if self.provider == "openai":
            return self._generate_openai(
                system_prompt,
                user_message,
                model_settings=model_settings,
                response_schema=response_schema,
                attachments=attachments,
            )
        return self._generate_google(
            system_prompt,
            user_message,
            model_settings=model_settings,
            response_schema=response_schema,
            attachments=attachments,
        )

    def _generate_google(
        self,
        system_prompt: str,
        user_message: str,
        model_settings: Optional[dict] = None,
        response_schema: Optional[type] = None,
        attachments: Sequence[ProviderFileAttachment] = (),
    ) -> LLMResult:
        overrides = model_settings or {}
        config_kwargs = {
            "system_instruction": system_prompt,
            "max_output_tokens": overrides.get(
                "max_output_tokens", settings.llm_max_output_tokens
            ),
        }
        if capabilities_for(self.model).supports_sampling_controls:
            config_kwargs["temperature"] = overrides.get(
                "temperature", settings.llm_temperature
            )
            config_kwargs["top_p"] = overrides.get("top_p", settings.llm_top_p)
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
            schema = _gemini_response_schema(schema)
            if isinstance(schema, dict):
                config_kwargs["response_json_schema"] = schema
            else:
                config_kwargs["response_schema"] = schema
        contents = user_message
        if attachments:
            contents = [
                types.Part.from_text(text=user_message),
                *[
                    types.Part.from_uri(
                        file_uri=attachment.uri,
                        mime_type=attachment.mime_type,
                    )
                    for attachment in attachments
                ],
            ]
        response = self._client.models.generate_content(
            model=self.model,
            config=types.GenerateContentConfig(**config_kwargs),
            contents=contents,
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

    def _generate_openai(
        self,
        system_prompt: str,
        user_message: str,
        *,
        model_settings: Optional[dict],
        response_schema: Optional[type],
        attachments: Sequence[ProviderFileAttachment],
    ) -> LLMResult:
        overrides = model_settings or {}
        content: list[dict[str, str]] = [{"type": "input_text", "text": user_message}]
        for attachment in attachments:
            if attachment.provider != "openai":
                raise ValueError("attachment provider does not match OpenAI client")
            content.append({"type": "input_file", "file_id": attachment.name})
        request = {
            "model": self.model,
            "instructions": system_prompt,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": overrides.get(
                "max_output_tokens", settings.llm_max_output_tokens
            ),
        }
        if response_schema is None:
            response = self._client.responses.create(**request)
        elif isinstance(response_schema, dict):
            response = self._client.responses.create(
                **request,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "structured_response",
                        "schema": response_schema,
                        "strict": True,
                    }
                },
            )
        else:
            response = self._client.responses.parse(
                **request,
                text_format=response_schema,
            )
        status = getattr(response, "status", None)
        incomplete_details = getattr(response, "incomplete_details", None)
        finish_reason = (
            getattr(incomplete_details, "reason", None)
            if status == "incomplete"
            else status
        )
        raw_text = getattr(response, "output_text", "") or ""
        parsed = getattr(response, "output_parsed", None)
        if parsed is not None:
            if hasattr(parsed, "model_dump_json"):
                raw_text = parsed.model_dump_json()
            elif isinstance(parsed, dict):
                raw_text = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
        result = LLMResult(
            raw_text=raw_text,
            provider_request_id=getattr(response, "id", None),
            model_name=self.model,
            model_version=getattr(response, "model", None),
            finish_reason=finish_reason,
            usage=_openai_usage_from_response(response),
        )
        if status == "incomplete":
            raise TruncatedResponseError(result)
        return result

    def upload_pdf(self, pdf: ValidatedReferencePdf) -> ProviderFileAttachment:
        if self.provider == "openai":
            uploaded = self._client.files.create(
                file=(pdf.filename, pdf.content, "application/pdf"),
                purpose="user_data",
            )
            return ProviderFileAttachment(
                name=uploaded.id,
                uri=uploaded.id,
                mime_type="application/pdf",
                provider="openai",
            )
        uploaded = self._client.files.upload(
            file=BytesIO(pdf.content),
            config=types.UploadFileConfig(
                display_name=pdf.filename,
                mime_type="application/pdf",
            ),
        )
        return ProviderFileAttachment(
            name=uploaded.name,
            uri=uploaded.uri,
            mime_type=uploaded.mime_type or "application/pdf",
        )

    def delete_file(self, name: str) -> None:
        if self.provider == "openai":
            self._client.files.delete(name)
            return
        self._client.files.delete(name=name)

    def generate_json(self, system_prompt: str, user_message: str) -> dict:
        result = self.generate(system_prompt, user_message)
        return _parse_json(result.raw_text)

    def generate_multimodal(
        self,
        system_prompt: str,
        user_message: str,
        inline_images: Sequence[dict],
        *,
        response_schema: type,
        model_settings: Optional[dict] = None,
    ) -> LLMResult:
        """Generate one structured response from bounded in-memory images."""
        if self.provider == "openai":
            content: list[dict[str, str]] = [{"type": "input_text", "text": user_message}]
            for image in inline_images:
                data = image.get("data")
                if not isinstance(data, bytes) or image.get("mime_type") != "image/png":
                    raise ValueError("only in-memory PNG review parts are supported")
                encoded = base64.b64encode(data).decode("ascii")
                content.append({"type": "input_image", "image_url": f"data:image/png;base64,{encoded}"})
            overrides = model_settings or {}
            response = self._client.responses.parse(
                model=self.model,
                instructions=system_prompt,
                input=[{"role": "user", "content": content}],
                max_output_tokens=overrides.get("max_output_tokens", settings.llm_max_output_tokens),
                text_format=response_schema,
            )
            status = getattr(response, "status", None)
            details = getattr(response, "incomplete_details", None)
            parsed = getattr(response, "output_parsed", None)
            raw_text = getattr(response, "output_text", "") or ""
            if parsed is not None and hasattr(parsed, "model_dump_json"):
                raw_text = parsed.model_dump_json()
            result = LLMResult(
                raw_text,
                getattr(response, "id", None),
                self.model,
                getattr(response, "model", None),
                getattr(details, "reason", None) if status == "incomplete" else status,
                _openai_usage_from_response(response),
            )
            if status == "incomplete":
                raise TruncatedResponseError(result)
            return result
        overrides = model_settings or {}
        parts = [types.Part.from_text(text=user_message)]
        for image in inline_images:
            data = image.get("data")
            if not isinstance(data, bytes) or image.get("mime_type") != "image/png":
                raise ValueError("only in-memory PNG review parts are supported")
            parts.append(types.Part.from_bytes(data=data, mime_type="image/png"))
        schema = _gemini_response_schema(response_schema.model_json_schema())
        config_kwargs = {
            "system_instruction": system_prompt,
            "max_output_tokens": overrides.get("max_output_tokens", settings.llm_max_output_tokens),
            "response_mime_type": "application/json",
            "response_json_schema": schema,
        }
        response = self._client.models.generate_content(
            model=self.model,
            config=types.GenerateContentConfig(**config_kwargs),
            contents=parts,
        )
        finish_reason = None
        if getattr(response, "candidates", None):
            finish_reason = getattr(response.candidates[0], "finish_reason", None)
            finish_reason = getattr(finish_reason, "value", finish_reason)
        result = LLMResult(response.text, getattr(response, "response_id", None), self.model, getattr(response, "model_version", None), finish_reason, _usage_from_response(response))
        if finish_reason in ("MAX_TOKENS", 2): raise TruncatedResponseError(result)
        return result


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
