import json
from types import SimpleNamespace

import pytest

from backend.services.docx_grounding import DocxGrounding
from backend.services.gemini_docx_authoring import (
    DOCX_AUTHORING_MODEL,
    AuthoringEnvelopeError,
    GeminiDocxAuthoringProvider,
)
from backend.services.llm_client import LLMResult


class FakeClient:
    model = DOCX_AUTHORING_MODEL
    def __init__(self, raw): self.raw, self.calls = raw, []
    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return LLMResult(self.raw, "response-1", self.model, "v1", "STOP")


def envelope(hash_value):
    return json.dumps({"schema_version": "docx-program-envelope/1", "language": "python", "entrypoint": "program.py", "program": "from docx import Document", "expected_outputs": ["assessment.docx", "assessment_manifest.json"], "grounding_sha256": hash_value, "generation_notes": "generated"})


def test_gemini_authoring_uses_strict_schema_grounding_and_attachments():
    grounding = DocxGrounding({"x": 1}, attachments=(SimpleNamespace(name="f", uri="u", mime_type="application/pdf"),))
    client = FakeClient(envelope(grounding.sha256))
    result = GeminiDocxAuthoringProvider(client).author_program(grounding, attempt_number=1)
    assert result.envelope.program.startswith("from docx")
    assert client.calls[0]["response_schema"].__name__ == "DocxProgramEnvelope"
    assert client.calls[0]["attachments"] == grounding.attachments
    assert "code_execution" not in repr(client.calls[0]).casefold()


def test_gemini_authoring_prompt_matches_luna_quality_contract_with_sandbox_limits():
    grounding = DocxGrounding({"x": 1})
    client = FakeClient(envelope(grounding.sha256))

    GeminiDocxAuthoringProvider(client).author_program(grounding, attempt_number=1)

    prompt = client.calls[0]["system_prompt"]
    for requirement in (
        "# Role",
        "# Personality",
        "# Measure of Success",
        "# Required Document Structure",
        "# Equation Rendering",
        "# Document Design",
        "# Verification",
        "editable native Microsoft Word equations",
        "dynamic `Page X of Y`",
        "accessible tables",
        "keep_with_next",
    ):
        assert requirement in prompt
    assert "/output/assessment.docx" in prompt
    assert "/output/assessment_manifest.json" in prompt
    assert "manifest_json_schema" in prompt
    assert "requirements.manifest_invariants" in prompt
    assert "/mnt/data/assessment.docx" not in prompt
    assert "Image Generation tool" not in prompt
    assert "Do not import `os`, `pathlib`, `sys`, `subprocess`, `zipfile`" in prompt


@pytest.mark.parametrize("raw", ["```json\n{}\n```", "prose {}", "{} {}"])
def test_gemini_authoring_rejects_non_envelope_output(raw):
    grounding = DocxGrounding({"x": 1})
    with pytest.raises(AuthoringEnvelopeError):
        GeminiDocxAuthoringProvider(FakeClient(raw)).author_program(grounding, attempt_number=1)
