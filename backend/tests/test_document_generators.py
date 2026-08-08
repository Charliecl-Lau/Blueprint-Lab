from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.models import Assessment, Run
from backend.services.document_generators import (
    GeminiLunaPairDocumentGenerator,
    LunaDirectDocumentGenerator,
    auto_download_docx,
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
        model="gpt-5.6-sol",
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


def generated_result(content=b"PK-direct-docx", request_id="resp-direct"):
    return LunaDocxResult(
        content=content,
        provider_result=LLMResult(
            "created",
            request_id,
            "gpt-5.6-sol",
            "gpt-5.6-sol-2026-08-01",
            "completed",
            TokenUsage(10, 5, 15, 2, 3, {}),
        ),
        container_id="container-1",
        file_id="file-1",
        filename="assessment.docx",
        prompt_sha256="c" * 64,
    )


def test_registry_resolves_all_document_backends():
    for backend in (
        "gemini_luna_pair",
        "luna_direct",
        "legacy",
        "self_hosted_code",
        "agentic_tools",
    ):
        assert document_generator_registry.get(backend) is not None


def test_auto_download_docx_uses_provider_specific_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.services.document_generators.settings.docx_auto_download_dir",
        str(tmp_path),
    )

    saved = auto_download_docx(run_id=42, provider="gemini", content=b"PK-docx")

    assert saved == tmp_path / "blueprint-lab-run-42-gemini.docx"
    assert saved.read_bytes() == b"PK-docx"
    assert list(tmp_path.iterdir()) == [saved]


def test_pair_generates_both_documents_from_the_same_run(test_db):
    run, _ = source_run(test_db)
    gemini = MagicMock()
    gemini.generate.return_value = SimpleNamespace(
        succeeded=True,
        canonicalized=False,
        safe_issue_codes=(),
        artifact_content=b"PK-gemini",
    )
    luna = MagicMock()
    luna.generate.return_value = SimpleNamespace(
        succeeded=True,
        canonicalized=True,
        safe_issue_codes=(),
        artifact_content=b"PK-luna",
    )
    downloader = MagicMock()

    result = GeminiLunaPairDocumentGenerator(
        gemini=gemini,
        luna=luna,
        downloader=downloader,
    ).generate(db=test_db, run=run)

    assert result.succeeded is True
    assert result.canonicalized is True
    assert gemini.generate.call_args.kwargs["run"] is run
    assert luna.generate.call_args.kwargs["run"] is run
    assert gemini.generate.call_args.kwargs["persist_artifact"] is False
    assert luna.generate.call_args.kwargs["persist_artifact"] is True
    assert [call.kwargs for call in downloader.call_args_list] == [
        {"run_id": run.id, "provider": "gemini", "content": b"PK-gemini"},
        {"run_id": run.id, "provider": "luna", "content": b"PK-luna"},
    ]


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
    provider.generate.assert_called_once_with(
        manifest, run_id=run.id, verification_feedback=()
    )
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
    assert provider.generate.call_count == 3
    assert provider.generate.call_args_list[1].kwargs["verification_feedback"] == (
        "canonical_question_missing: no additional evidence",
    )
    assert provider.generate.call_args_list[2].kwargs["verification_feedback"] == (
        "canonical_question_missing: no additional evidence",
    )
    session = run.luna_docx_sessions[-1]
    assert session.outcome == "failed"
    assert session.attempt_count == 3
    assert session.repair_count == 2
    assert session.final_issue_codes == ["canonical_question_missing"]
    assert len(session.attempts) == 3
    assert all(item.validation_report["valid"] is False for item in session.attempts)


def test_luna_direct_repairs_once_with_machine_feedback(test_db):
    run, manifest = source_run(test_db)
    provider = MagicMock()
    provider.generate.side_effect = [
        generated_result(b"PK-invalid", "resp-invalid"),
        generated_result(b"PK-repaired", "resp-repaired"),
    ]
    verifier = MagicMock()
    verifier.verify.side_effect = [
        VerificationReport(
            False,
            (VerificationIssue("native_equation_structure_invalid", evidence="equation index 2: subscript"),),
        ),
        VerificationReport(True, ()),
    ]

    result = LunaDirectDocumentGenerator(provider, verifier).generate(
        db=test_db, run=run
    )

    assert result.succeeded is True
    assert provider.generate.call_args_list[1].kwargs["verification_feedback"] == (
        "native_equation_structure_invalid: equation index 2: subscript",
    )
    assert run.document_artifact.content == b"PK-repaired"
    assert [item.attempt for item in run.model_call_usages[-2:]] == [1, 2]
    session = run.luna_docx_sessions[-1]
    assert session.outcome == "succeeded"
    assert session.attempt_count == 2
    assert session.repair_count == 1
    assert session.final_artifact_sha256
    assert session.attempts[0].repair_feedback["issues"][0]["code"] == (
        "native_equation_structure_invalid"
    )
    assert session.attempts[1].validation_report["valid"] is True


def test_luna_direct_does_not_repair_nonrepairable_evidence(test_db):
    run, _ = source_run(test_db)
    provider = MagicMock()
    provider.generate.return_value = generated_result()
    verifier = MagicMock()
    verifier.verify.return_value = VerificationReport(
        False,
        (VerificationIssue("docx_package_invalid", repairable=False, evidence="macro_content"),),
    )

    result = LunaDirectDocumentGenerator(provider, verifier).generate(db=test_db, run=run)

    assert result.succeeded is False
    assert provider.generate.call_count == 1
    session = run.luna_docx_sessions[-1]
    assert session.repair_count == 0
    assert session.attempt_count == 1
    assert session.outcome == "failed"


def test_luna_pipeline_reuses_cycle_scoped_provider_session(test_db):
    run, _ = source_run(test_db)
    provider = MagicMock()
    provider.supports_reusable_session = True
    container_session = SimpleNamespace(container_id="container-shared")
    provider.create_session.return_value = container_session
    provider.close_session.return_value = True
    provider.generate.side_effect = [
        generated_result(b"PK-invalid", "resp-cycle-1"),
        generated_result(b"PK-valid", "resp-cycle-2"),
    ]
    verifier = MagicMock()
    verifier.verify.side_effect = [
        VerificationReport(False, (VerificationIssue("header_missing"),)),
        VerificationReport(True, ()),
    ]

    result = LunaDirectDocumentGenerator(provider, verifier).generate(db=test_db, run=run)

    assert result.succeeded is True
    provider.create_session.assert_called_once()
    assert all(
        item.kwargs["session"] is container_session
        for item in provider.generate.call_args_list
    )
    provider.close_session.assert_called_once_with(container_session)
    assert run.luna_docx_sessions[-1].container_id == "container-shared"
