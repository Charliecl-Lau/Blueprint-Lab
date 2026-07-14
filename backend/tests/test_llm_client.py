import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from backend.config import settings
from backend.services.llm_client import (
    LLMClient,
    LLMResult,
    TokenUsage,
    TruncatedResponseError,
)
from backend.schemas.assessment_schema import AssessmentGenerationResponse


@contextmanager
def client_for_response(response):
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        mock_client.return_value.models.generate_content.return_value = response
        yield LLMClient()


def gemini_response(finish_reason="STOP"):
    return SimpleNamespace(
        text="result",
        response_id="response-1",
        model_version="v1",
        candidates=[SimpleNamespace(finish_reason=finish_reason)],
        usage_metadata=SimpleNamespace(
            prompt_token_count=100,
            candidates_token_count=40,
            total_token_count=155,
            cached_content_token_count=20,
            thoughts_token_count=15,
            tool_use_prompt_token_count=3,
        ),
    )


def test_llm_client_installs_event_loop_when_worker_thread_has_none():
    new_loop = MagicMock()
    with (
        patch.object(asyncio, "get_event_loop", side_effect=RuntimeError("no current event loop")),
        patch.object(asyncio, "new_event_loop", return_value=new_loop) as create_loop,
        patch.object(asyncio, "set_event_loop") as set_loop,
        patch("backend.services.llm_client.genai.Client") as mock_client,
    ):
        from backend.services.llm_client import LLMClient

        LLMClient()

    create_loop.assert_called_once_with()
    set_loop.assert_has_calls([call(new_loop)])
    mock_client.assert_called_once()


def test_llm_client_calls_generate_content():
    with patch("backend.services.llm_client.genai.Client") as MockClient:
        mock_response = MagicMock()
        mock_response.text = '{"generated_prompt": "test prompt"}'
        mock_response.response_id = None
        mock_response.model_version = None
        mock_response.candidates = []
        mock_response.usage_metadata = None
        MockClient.return_value.models.generate_content.return_value = mock_response

        from backend.services.llm_client import LLMClient
        client = LLMClient()
        result = client.generate(
            system_prompt="You are a test assistant.",
            user_message="Generate something.",
        )

        assert result == LLMResult(
            raw_text='{"generated_prompt": "test prompt"}',
            provider_request_id=None,
            model_name=settings.llm_model,
            model_version=None,
            finish_reason=None,
            usage=None,
        )
        MockClient.return_value.models.generate_content.assert_called_once()


def test_llm_client_passes_model_name():
    with patch("backend.services.llm_client.genai.Client") as MockClient:
        mock_response = MagicMock()
        mock_response.text = "result"
        MockClient.return_value.models.generate_content.return_value = mock_response

        from backend.services.llm_client import LLMClient
        client = LLMClient(model="gemma-4-31b-it")
        client.generate("system", "user")

        call_kwargs = MockClient.return_value.models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == "gemma-4-31b-it"


def test_llm_client_passes_provider_structured_output_schema():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        response = MagicMock()
        response.text = '{"questions": []}'
        response.candidates = []
        mock_client.return_value.models.generate_content.return_value = response

        from backend.services.llm_client import LLMClient

        LLMClient().generate(
            "system",
            "user",
            response_schema=AssessmentGenerationResponse,
        )

        config = mock_client.return_value.models.generate_content.call_args.kwargs["config"]
        assert config.response_mime_type == "application/json"
        assert isinstance(config.response_schema, dict)
        assert "questions" in config.response_schema["properties"]

        def contains_default(value):
            if isinstance(value, dict):
                return "default" in value or any(contains_default(item) for item in value.values())
            if isinstance(value, list):
                return any(contains_default(item) for item in value)
            return False

        assert not contains_default(config.response_schema)


def test_llm_client_uses_configured_model_defaults_without_thinking_override():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        response = MagicMock()
        response.text = "result"
        response.candidates = []
        mock_client.return_value.models.generate_content.return_value = response

        from backend.services.llm_client import LLMClient

        LLMClient().generate("system", "user")

        config = mock_client.return_value.models.generate_content.call_args.kwargs["config"]
        assert config.thinking_config is None


def test_llm_client_raises_on_truncated_response():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        response = MagicMock()
        response.text = '{"questions": [{"body": "trunca'
        candidate = MagicMock()
        candidate.finish_reason = "MAX_TOKENS"
        response.candidates = [candidate]
        response.usage_metadata = None
        mock_client.return_value.models.generate_content.return_value = response

        from backend.services.llm_client import LLMClient, TruncatedResponseError

        try:
            LLMClient().generate("system", "user")
            assert False, "expected TruncatedResponseError"
        except TruncatedResponseError as exc:
            assert "MAX_TOKENS" in str(exc)


def test_llm_client_passes_explicit_model_settings_and_returns_metadata():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        response = MagicMock()
        response.text = " untouched \n"
        response.response_id = "request-123"
        response.model_version = "gemma-version-1"
        candidate = MagicMock()
        candidate.finish_reason = "STOP"
        response.candidates = [candidate]
        response.usage_metadata = None
        mock_client.return_value.models.generate_content.return_value = response

        from backend.services.llm_client import LLMClient

        result = LLMClient().generate("system", "user")

        config = mock_client.return_value.models.generate_content.call_args.kwargs["config"]
        assert config.temperature == 0.2
        assert config.top_p == 0.95
        assert config.seed is None
        assert config.max_output_tokens == settings.llm_max_output_tokens
        assert result.raw_text == " untouched \n"
        assert result.provider_request_id == "request-123"
        assert result.model_name == settings.llm_model
        assert result.model_version == "gemma-version-1"
        assert result.finish_reason == "STOP"
        assert result.usage is None


def test_llm_client_returns_api_reported_usage_without_combining_categories():
    response = gemini_response()
    with client_for_response(response) as client:
        result = client.generate("system", "user")

    assert result.usage == TokenUsage(
        input_tokens=100,
        output_tokens=40,
        total_tokens=155,
        cached_content_tokens=20,
        reasoning_tokens=15,
        extra_token_counts={"tool_use_prompt_token_count": 3},
    )


def test_truncated_response_error_preserves_usage():
    response = gemini_response("MAX_TOKENS")
    with pytest.raises(TruncatedResponseError) as raised:
        with client_for_response(response) as client:
            client.generate("system", "user")

    assert raised.value.result.usage.total_tokens == 155
