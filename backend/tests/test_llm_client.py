import asyncio
from unittest.mock import MagicMock, call, patch

from backend.services.llm_client import LLMResult
from backend.schemas.assessment_schema import AssessmentGenerationResponse


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
            model_name="gemma-4-31b-it",
            model_version=None,
            finish_reason=None,
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


def test_llm_client_disables_thinking_budget():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        response = MagicMock()
        response.text = "result"
        response.candidates = []
        mock_client.return_value.models.generate_content.return_value = response

        from backend.services.llm_client import LLMClient

        LLMClient().generate("system", "user")

        config = mock_client.return_value.models.generate_content.call_args.kwargs["config"]
        assert config.thinking_config is not None
        assert config.thinking_config.thinking_budget == 0


def test_llm_client_raises_on_truncated_response():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        response = MagicMock()
        response.text = '{"questions": [{"body": "trunca'
        candidate = MagicMock()
        candidate.finish_reason = "MAX_TOKENS"
        response.candidates = [candidate]
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
        mock_client.return_value.models.generate_content.return_value = response

        from backend.services.llm_client import LLMClient

        result = LLMClient().generate("system", "user")

        config = mock_client.return_value.models.generate_content.call_args.kwargs["config"]
        assert config.temperature == 0.2
        assert config.top_p == 0.95
        assert config.seed is None
        assert config.max_output_tokens == 8192
        assert result.raw_text == " untouched \n"
        assert result.provider_request_id == "request-123"
        assert result.model_name == "gemma-4-31b-it"
        assert result.model_version == "gemma-version-1"
        assert result.finish_reason == "STOP"
