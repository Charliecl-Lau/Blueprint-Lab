from unittest.mock import MagicMock, patch

from backend.services.llm_client import LLMResult


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
            model_name="gemma-4-31b",
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
        client = LLMClient(model="gemma-4-31b")
        client.generate("system", "user")

        call_kwargs = MockClient.return_value.models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == "gemma-4-31b"


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
        assert result.model_name == "gemma-4-31b"
        assert result.model_version == "gemma-version-1"
        assert result.finish_reason == "STOP"
