from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.config import settings
from backend.services.luna_direct_docx_provider import (
    LUNA_DIRECT_MODEL,
    LunaDirectDocxProvider,
    LunaDocxGenerationError,
)
from backend.services.reproducibility import canonical_json


def docx_bytes():
    target = BytesIO()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<w:document />")
    return target.getvalue()


def response(citations, *, status="completed"):
    return SimpleNamespace(
        id="resp-docx",
        model="gpt-5.6-luna-2026-08-01",
        status=status,
        output_text="Created the assessment.",
        output=[SimpleNamespace(content=[SimpleNamespace(annotations=citations)])],
        usage=None,
    )


def citation(filename="assessment.docx", *, container_id="container-1"):
    return SimpleNamespace(
        type="container_file_citation",
        container_id=container_id,
        file_id="file-1",
        filename=filename,
    )


def configured_provider(citations=None, *, status="completed", content=None):
    client = MagicMock()
    client.containers.create.return_value = SimpleNamespace(id="container-1")
    client.containers.files.create.return_value = SimpleNamespace(
        path="/mnt/data/hash-assessment.json"
    )
    client.responses.create.return_value = response(
        [citation()] if citations is None else citations,
        status=status,
    )
    client.containers.files.content.retrieve.return_value = BytesIO(
        docx_bytes() if content is None else content
    )
    return LunaDirectDocxProvider(client=client), client


def test_configures_a_bounded_provider_request_without_hidden_retries():
    with patch("backend.services.luna_direct_docx_provider.OpenAI") as client_type:
        LunaDirectDocxProvider()

    client_type.assert_called_once_with(
        api_key=settings.openai_api_key,
        timeout=settings.docx_tool_provider_timeout_seconds,
        max_retries=0,
    )


def test_generates_and_downloads_one_docx_before_container_cleanup():
    provider, client = configured_provider()
    assessment = {"questions": [{"model_answer": "Answer", "body": "Question"}]}

    result = provider.generate(assessment, run_id=42)

    create = client.containers.create.call_args.kwargs
    assert create["extra_body"] == {"memory_limit": "1g"}
    request = client.responses.create.call_args.kwargs
    assert request["model"] == LUNA_DIRECT_MODEL
    assert request["tools"] == [
        {"type": "code_interpreter", "container": "container-1"}
    ]
    assert request["tool_choice"] == "required"
    assert "Student-Facing Questions" in request["instructions"]
    assert "Fully Worked Solutions" in request["instructions"]
    assert "never put source notation such as `x_a`" in request["instructions"]
    assert "Page X of Y" in request["instructions"]
    client.containers.files.create.assert_called_once_with(
        "container-1",
        file=(
            "assessment.json",
            canonical_json(assessment).encode("utf-8"),
            "application/json",
        ),
    )
    input_text = request["input"][0]["content"][0]["text"]
    assert "/mnt/data/hash-assessment.json" in input_text
    assert canonical_json(assessment) in input_text
    assert result.content == docx_bytes()
    assert result.filename == "assessment.docx"
    assert result.provider_result.provider_request_id == "resp-docx"
    assert client.mock_calls.index(
        call.containers.files.content.retrieve("file-1", container_id="container-1")
    ) < client.mock_calls.index(call.containers.delete("container-1"))


def test_includes_machine_feedback_for_a_repair_attempt():
    provider, client = configured_provider()

    provider.generate(
        {"questions": []},
        run_id=42,
        verification_feedback=(
            "native_equation_structure_invalid: equation index 2: subscript",
        ),
    )

    instructions = client.responses.create.call_args.kwargs["instructions"]
    assert "# Machine Verification Repair" in instructions
    assert "equation index 2: subscript" in instructions


def test_rejects_a_canonical_upload_without_a_mounted_path():
    provider, client = configured_provider()
    client.containers.files.create.return_value = SimpleNamespace()

    with pytest.raises(LunaDocxGenerationError) as raised:
        provider.generate({"questions": []}, run_id=42)

    assert raised.value.code == "canonical_file_upload_invalid"
    client.responses.create.assert_not_called()
    client.containers.delete.assert_called_once_with("container-1")


@pytest.mark.parametrize(
    "citations",
    [[], [citation(), citation("second.docx")], [citation("assessment.pdf")]],
)
def test_rejects_invalid_docx_citation_contract(citations):
    provider, client = configured_provider(citations)

    with pytest.raises(LunaDocxGenerationError) as raised:
        provider.generate({"questions": []}, run_id=1)

    assert raised.value.code == "docx_citation_invalid"
    client.containers.delete.assert_called_once_with("container-1")


@pytest.mark.parametrize(
    ("status", "content", "maximum_bytes", "code"),
    [
        ("incomplete", None, None, "docx_response_incomplete"),
        ("completed", b"", None, "docx_content_empty"),
        ("completed", b"not-a-zip", None, "docx_package_invalid"),
        ("completed", None, 2, "docx_artifact_too_large"),
    ],
)
def test_rejects_unsafe_provider_results(status, content, maximum_bytes, code):
    provider, client = configured_provider(status=status, content=content)
    if maximum_bytes is not None:
        provider.maximum_bytes = maximum_bytes

    with pytest.raises(LunaDocxGenerationError) as raised:
        provider.generate({"questions": []}, run_id=1)

    assert raised.value.code == code
    client.containers.delete.assert_called_once_with("container-1")
