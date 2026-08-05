import asyncio
from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from google.genai import errors as genai_errors

from backend.config import Settings, settings
from backend.services.llm_client import (
    LLMClient,
    LLMResult,
    TokenUsage,
    TruncatedResponseError,
    is_retryable_provider_error,
)
from backend.schemas.assessment_schema import AssessmentGenerationResponse
from backend.services.reference_pdfs import (
    ProviderFileAttachment,
    ValidatedReferencePdf,
)


@contextmanager
def client_for_response(response):
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        mock_client.return_value.models.generate_content.return_value = response
        yield LLMClient(provider="google")


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


@pytest.mark.parametrize("status_code", [500, 503, 599])
def test_server_errors_are_retryable(status_code):
    error = genai_errors.ServerError(
        status_code,
        {"error": {"code": status_code, "status": "UNAVAILABLE"}},
    )

    assert is_retryable_provider_error(error) is True


@pytest.mark.parametrize("status_code", [408, 409, 429])
def test_transient_client_errors_are_retryable(status_code):
    error = genai_errors.ClientError(
        status_code,
        {"error": {"code": status_code, "status": "RESOURCE_EXHAUSTED"}},
    )

    assert is_retryable_provider_error(error) is True


def test_permanent_provider_and_local_errors_are_not_retryable():
    error = genai_errors.ClientError(
        400,
        {"error": {"code": 400, "status": "INVALID_ARGUMENT"}},
    )

    assert is_retryable_provider_error(error) is False
    assert is_retryable_provider_error(ValueError("invalid tool turn")) is False


def test_llm_client_installs_event_loop_when_worker_thread_has_none():
    new_loop = MagicMock()
    with (
        patch.object(asyncio, "get_event_loop", side_effect=RuntimeError("no current event loop")),
        patch.object(asyncio, "new_event_loop", return_value=new_loop) as create_loop,
        patch.object(asyncio, "set_event_loop") as set_loop,
        patch("backend.services.llm_client.genai.Client") as mock_client,
    ):
        from backend.services.llm_client import LLMClient

        LLMClient(provider="google")

    create_loop.assert_called_once_with()
    set_loop.assert_has_calls([call(new_loop)])
    mock_client.assert_called_once()


def test_llm_client_configures_sixty_second_provider_timeout():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        LLMClient(provider="google")

    kwargs = mock_client.call_args.kwargs
    assert kwargs["api_key"] == settings.google_api_key
    assert kwargs["http_options"].timeout == 60_000


def test_llm_client_accepts_a_longer_provider_timeout():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        LLMClient(provider="google", timeout_ms=120_000)

    kwargs = mock_client.call_args.kwargs
    assert kwargs["http_options"].timeout == 120_000


def test_llm_client_rejects_nonpositive_provider_timeout():
    with pytest.raises(ValueError, match="provider timeout must be positive"):
        LLMClient(timeout_ms=0)


def test_openai_luna_is_the_default_provider_and_model():
    configured = Settings(_env_file=None)
    assert configured.llm_provider == "openai"
    assert configured.llm_model == "gpt-5.6-luna"
    assert Settings(_env_file=None).docx_tool_provider_timeout_seconds == 120


def test_gemini_35_omits_legacy_sampling_fields():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        mock_client.return_value.models.generate_content.return_value = gemini_response()

        LLMClient(provider="google", model="gemini-3.5-flash-lite").generate(
            "system",
            "user",
            model_settings={"temperature": 0.7, "top_p": 0.8, "seed": 42},
        )

    config = mock_client.return_value.models.generate_content.call_args.kwargs["config"]
    dumped = config.model_dump(exclude_none=True)
    assert "temperature" not in dumped
    assert "top_p" not in dumped
    assert "seed" not in dumped
    assert dumped["max_output_tokens"] == settings.llm_max_output_tokens


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
        client = LLMClient(provider="google")
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
        client = LLMClient(provider="google", model="gemma-4-31b-it")
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

        LLMClient(provider="google").generate(
            "system",
            "user",
            response_schema=AssessmentGenerationResponse,
        )

        config = mock_client.return_value.models.generate_content.call_args.kwargs["config"]
        assert config.response_mime_type == "application/json"
        assert config.response_schema is None
        assert isinstance(config.response_json_schema, dict)
        assert "questions" in config.response_json_schema["properties"]

        def contains_default(value):
            if isinstance(value, dict):
                return "default" in value or any(contains_default(item) for item in value.values())
            if isinstance(value, list):
                return any(contains_default(item) for item in value)
            return False

        assert not contains_default(config.response_json_schema)


def test_llm_client_uses_json_schema_for_canonical_assessment_contract():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        response = MagicMock()
        response.text = '{"questions": []}'
        response.candidates = []
        mock_client.return_value.models.generate_content.return_value = response

        from backend.schemas.assessment_schema import ASSESSMENT_PROVIDER_SCHEMA
        from backend.services.llm_client import LLMClient

        LLMClient(provider="google").generate(
            "system",
            "user",
            response_schema=ASSESSMENT_PROVIDER_SCHEMA,
        )

        config = mock_client.return_value.models.generate_content.call_args.kwargs["config"]
        assert config.response_json_schema["properties"]["questions"]
        assert config.response_schema is None


def test_llm_client_uses_json_schema_for_pydantic_contract_without_defs():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        response = MagicMock()
        response.text = '{"schema_version": "docx-program-envelope/1"}'
        response.candidates = []
        mock_client.return_value.models.generate_content.return_value = response

        from backend.schemas.docx_authoring_schema import DocxProgramEnvelope
        from backend.services.llm_client import LLMClient

        LLMClient(provider="google").generate(
            "system",
            "user",
            response_schema=DocxProgramEnvelope,
        )

        config = mock_client.return_value.models.generate_content.call_args.kwargs["config"]
        assert config.response_schema is None
        assert "additionalProperties" not in config.response_json_schema
        assert "program" in config.response_json_schema["properties"]


def test_llm_client_uses_configured_model_defaults_without_thinking_override():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        response = MagicMock()
        response.text = "result"
        response.candidates = []
        mock_client.return_value.models.generate_content.return_value = response

        from backend.services.llm_client import LLMClient

        LLMClient(provider="google").generate("system", "user")

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
            LLMClient(provider="google").generate("system", "user")
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

        result = LLMClient(provider="google", model="gemma-4-31b-it").generate("system", "user")

        config = mock_client.return_value.models.generate_content.call_args.kwargs["config"]
        assert config.temperature == 0.2
        assert config.top_p == 0.95
        assert config.seed is None
        assert config.max_output_tokens == settings.llm_max_output_tokens
        assert result.raw_text == " untouched \n"
        assert result.provider_request_id == "request-123"
        assert result.model_name == "gemma-4-31b-it"
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


def test_llm_client_uploads_pdf_with_safe_provider_metadata():
    pdf = ValidatedReferencePdf("reference.pdf", b"%PDF-1.7\nvalid")
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        mock_client.return_value.files.upload.return_value = SimpleNamespace(
            name="files/reference-1",
            uri="https://files/reference-1",
            mime_type="application/pdf",
        )

        attachment = LLMClient(provider="google").upload_pdf(pdf)

    call_kwargs = mock_client.return_value.files.upload.call_args.kwargs
    assert isinstance(call_kwargs["file"], BytesIO)
    assert call_kwargs["file"].getvalue() == b"%PDF-1.7\nvalid"
    assert call_kwargs["config"].display_name == "reference.pdf"
    assert call_kwargs["config"].mime_type == "application/pdf"
    assert attachment == ProviderFileAttachment(
        name="files/reference-1",
        uri="https://files/reference-1",
        mime_type="application/pdf",
    )


def test_llm_client_attaches_ordered_provider_files():
    attachments = [
        ProviderFileAttachment(
            "files/one", "https://files/one", "application/pdf"
        ),
        ProviderFileAttachment(
            "files/two", "https://files/two", "application/pdf"
        ),
    ]
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        mock_client.return_value.models.generate_content.return_value = gemini_response()

        LLMClient(provider="google").generate("system", "user", attachments=attachments)

    contents = (
        mock_client.return_value.models.generate_content.call_args.kwargs["contents"]
    )
    assert contents[0].text == "user"
    assert [part.file_data.file_uri for part in contents[1:]] == [
        "https://files/one",
        "https://files/two",
    ]


def test_llm_client_keeps_text_only_contents_unchanged():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        mock_client.return_value.models.generate_content.return_value = gemini_response()

        LLMClient(provider="google").generate("system", "user", attachments=[])

    assert (
        mock_client.return_value.models.generate_content.call_args.kwargs["contents"]
        == "user"
    )


def test_llm_client_deletes_provider_file_by_name():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        LLMClient(provider="google").delete_file("files/reference-1")

    mock_client.return_value.files.delete.assert_called_once_with(
        name="files/reference-1"
    )


def openai_response(*, status="completed", output_text="result"):
    return SimpleNamespace(
        id="resp_123",
        model="gpt-5.6-luna-2026-08-01",
        status=status,
        output_text=output_text,
        output_parsed=None,
        incomplete_details=(
            SimpleNamespace(reason="max_output_tokens")
            if status == "incomplete"
            else None
        ),
        usage=SimpleNamespace(
            input_tokens=120,
            output_tokens=50,
            total_tokens=170,
            input_tokens_details=SimpleNamespace(cached_tokens=25),
            output_tokens_details=SimpleNamespace(reasoning_tokens=15),
        ),
    )


def test_openai_client_constructs_responses_request_with_ordered_files():
    attachments = [
        ProviderFileAttachment("file-one", "file-one", "application/pdf", "openai"),
        ProviderFileAttachment("file-two", "file-two", "application/pdf", "openai"),
    ]
    with patch("backend.services.llm_client.OpenAI") as client_type:
        client_type.return_value.responses.create.return_value = openai_response()

        result = LLMClient(provider="openai", model="gpt-5.6-luna").generate(
            "system", "user", attachments=attachments
        )

    client_type.assert_called_once_with(api_key=settings.openai_api_key, timeout=60.0)
    request = client_type.return_value.responses.create.call_args.kwargs
    assert request["model"] == "gpt-5.6-luna"
    assert request["instructions"] == "system"
    assert request["input"][0]["content"] == [
        {"type": "input_text", "text": "user"},
        {"type": "input_file", "file_id": "file-one"},
        {"type": "input_file", "file_id": "file-two"},
    ]
    assert result.provider_request_id == "resp_123"
    assert result.model_version == "gpt-5.6-luna-2026-08-01"
    assert result.usage == TokenUsage(120, 50, 170, 25, 15, {})


def test_openai_client_uses_responses_parse_for_pydantic_output():
    with patch("backend.services.llm_client.OpenAI") as client_type:
        response = openai_response(output_text='{"questions": []}')
        client_type.return_value.responses.parse.return_value = response

        LLMClient(provider="openai", model="gpt-5.6-luna").generate(
            "system",
            "user",
            response_schema=AssessmentGenerationResponse,
        )

    request = client_type.return_value.responses.parse.call_args.kwargs
    assert request["text_format"] is AssessmentGenerationResponse
    assert not client_type.return_value.responses.create.called


def test_openai_client_uses_strict_text_format_for_json_schema_dict():
    schema = {
        "type": "object",
        "properties": {"questions": {"type": "array", "items": {"type": "string"}}},
        "required": ["questions"],
        "additionalProperties": False,
    }
    with patch("backend.services.llm_client.OpenAI") as client_type:
        client_type.return_value.responses.create.return_value = openai_response(
            output_text='{"questions": []}'
        )

        LLMClient(provider="openai", model="gpt-5.6-luna").generate(
            "system", "user", response_schema=schema
        )

    request = client_type.return_value.responses.create.call_args.kwargs
    strict_schema = request["text"]["format"]["schema"]
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["name"] == "structured_response"
    assert request["text"]["format"]["strict"] is True
    assert strict_schema["required"] == ["questions"]
    assert strict_schema["additionalProperties"] is False
    assert not client_type.return_value.responses.parse.called


def test_openai_strict_schema_requires_defaulted_nested_assessment_fields():
    from backend.schemas.assessment_schema import ASSESSMENT_PROVIDER_SCHEMA

    with patch("backend.services.llm_client.OpenAI") as client_type:
        client_type.return_value.responses.create.return_value = openai_response(
            output_text='{"questions": []}'
        )

        LLMClient(provider="openai", model="gpt-5.6-luna").generate(
            "system", "user", response_schema=ASSESSMENT_PROVIDER_SCHEMA
        )

    strict_schema = client_type.return_value.responses.create.call_args.kwargs[
        "text"
    ]["format"]["schema"]
    question = strict_schema["$defs"]["ProviderQuestionResponse"]
    assert set(question["required"]) == set(question["properties"])
    assert "options" in question["required"]
    assert "quality_checks" in question["required"]
    assert "default" not in question["properties"]["options"]


def test_openai_incomplete_response_preserves_reason_and_usage():
    with patch("backend.services.llm_client.OpenAI") as client_type:
        client_type.return_value.responses.create.return_value = openai_response(
            status="incomplete", output_text="partial"
        )

        with pytest.raises(TruncatedResponseError) as raised:
            LLMClient(provider="openai", model="gpt-5.6-luna").generate(
                "system", "user"
            )

    assert raised.value.result.finish_reason == "max_output_tokens"
    assert raised.value.result.usage.reasoning_tokens == 15


def test_openai_uploads_and_deletes_pdf_file():
    pdf = ValidatedReferencePdf("reference.pdf", b"%PDF-1.7\nvalid")
    with patch("backend.services.llm_client.OpenAI") as client_type:
        client_type.return_value.files.create.return_value = SimpleNamespace(id="file-123")
        client = LLMClient(provider="openai", model="gpt-5.6-luna")

        attachment = client.upload_pdf(pdf)
        client.delete_file(attachment.name)

    assert attachment == ProviderFileAttachment(
        "file-123", "file-123", "application/pdf", "openai"
    )
    client_type.return_value.files.create.assert_called_once_with(
        file=("reference.pdf", pdf.content, "application/pdf"), purpose="user_data"
    )
    client_type.return_value.files.delete.assert_called_once_with("file-123")
