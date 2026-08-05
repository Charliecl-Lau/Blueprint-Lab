from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.models import Assessment, Run
from backend.services.document_generators import (
    LunaDirectDocumentGenerator,
    document_generator_registry,
)
from backend.services.docx_verification import VerificationIssue, VerificationReport
from backend.services.llm_client import LLMResult, TokenUsage
from backend.services.luna_direct_docx_provider import (
    LunaDocxGenerationError,
    LunaDocxResult,
)
from backend.tests.test_api_runs import _experiment_and_condition


def source_run(db):
    experiment, condition = _experiment_and_condition(db)
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="documenting",
        provider="openai",
        model="gpt-5.6-luna",
        model_settings={},
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        model_call_count=0,
    )
    manifest = {
        "questions": [
            {"body": "Question text", "model_answer": "Solution text", "equations": []}
        ]
    }
    original = Assessment(
        version=1,
        kind="original_generation",
        raw_response_text="canonical",
        parsed_json=manifest,
        output_hash="a" * 64,
        parsed_json_hash="b" * 64,
        schema_version="1",
        validation_status="valid",
    )
    run.assessment_versions.append(original)
    run.canonical_assessment = original
    db.add(run)
    db.commit()
    return run, deepcopy(manifest)


def generated_result(content=b"PK-direct-docx"):
    return LunaDocxResult(
        content=content,
        provider_result=LLMResult(
            "created",
            "resp-direct",
            "gpt-5.6-luna",
            "gpt-5.6-luna-2026-08-01",
            "completed",
            TokenUsage(10, 5, 15, 2, 3, {}),
        ),
        container_id="container-1",
        file_id="file-1",
        filename="assessment.docx",
        prompt_sha256="c" * 64,
    )


def test_registry_resolves_all_four_document_backends():
    for backend in ("luna_direct", "legacy", "self_hosted_code", "agentic_tools"):
        assert document_generator_registry.get(backend) is not None


def test_luna_direct_persists_verified_artifact_without_rendering(test_db):
    run, manifest = source_run(test_db)
    provider = MagicMock()
    provider.generate.return_value = generated_result()
    verifier = MagicMock()
    verifier.verify.return_value = VerificationReport(True, ())
    progress = MagicMock()

    with patch("backend.services.document_generators.DocxVisualRenderer") as renderer:
        result = LunaDirectDocumentGenerator(provider, verifier).generate(
            db=test_db, run=run, progress=progress
        )

    assert result.succeeded is True
    provider.generate.assert_called_once_with(manifest, run_id=run.id)
    verifier.verify.assert_called_once_with(b"PK-direct-docx", manifest)
    renderer.assert_not_called()
    assert progress.call_args_list[0].args == ("docx_authoring",)
    assert progress.call_args_list[1].args == ("docx_validating",)
    assert len(run.assessment_versions) == 2
    assert run.canonical_assessment.version == 2
    assert run.canonical_assessment.parsed_json == manifest
    assert run.document_artifact.content == b"PK-direct-docx"
    assert run.model_call_usages[-1].stage == "docx_direct_generation"
    assert run.total_tokens == 15


def test_luna_direct_provider_failure_preserves_original_assessment(test_db):
    run, manifest = source_run(test_db)
    original_id = run.canonical_assessment.id
    provider = MagicMock()
    provider.generate.side_effect = LunaDocxGenerationError("docx_citation_invalid")

    result = LunaDirectDocumentGenerator(provider, MagicMock()).generate(
        db=test_db, run=run
    )

    assert result.succeeded is False
    assert result.safe_issue_codes == ("docx_citation_invalid",)
    assert run.canonical_assessment_id == original_id
    assert run.canonical_assessment.parsed_json == manifest
    assert run.document_artifact is None


def test_luna_direct_verification_failure_preserves_original_assessment(test_db):
    run, manifest = source_run(test_db)
    original_id = run.canonical_assessment.id
    provider = MagicMock()
    provider.generate.return_value = generated_result()
    verifier = MagicMock()
    verifier.verify.return_value = VerificationReport(
        False, (VerificationIssue("canonical_question_missing"),)
    )

    result = LunaDirectDocumentGenerator(provider, verifier).generate(
        db=test_db, run=run
    )

    assert result.succeeded is False
    assert result.safe_issue_codes == ("canonical_question_missing",)
    assert run.canonical_assessment_id == original_id
    assert run.canonical_assessment.parsed_json == manifest
    assert run.document_artifact is None
    assert run.model_call_usages[-1].stage == "docx_direct_generation"
