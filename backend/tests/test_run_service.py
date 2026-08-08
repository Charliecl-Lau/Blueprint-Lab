import hashlib
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from backend.models.experiment import Condition, Experiment
from backend.models.run import (
    Assessment,
    DocumentArtifact,
    Prompt,
    Run,
    RunReferencePdf,
)
from backend.models.source_document import SourceDocument
from backend.schemas.run_schema import ModelSettings, SourceBinding
from backend.services.assessment_evaluation import persist_assessment_questions
from backend.services.run_service import create_run, retry_llm_evaluation, retry_run
from backend.config import settings


def condition(db):
    experiment = Experiment(course="C", topic="T", learning_objectives=["L"], assessment_type="mixed", difficulty="D", number_of_questions=1)
    db.add(experiment); db.flush()
    value = Condition(experiment_id=experiment.id, prompt_structure="openai", factor_inputs={}, condition_label="test")
    db.add(value); db.flush()
    return value


def test_retry_creates_next_run_without_mutating_original(test_db):
    item = condition(test_db)
    original = create_run(test_db, item.id, [], ModelSettings(provider="openai", model="gpt-test", temperature=0.2))
    original.status = "complete"
    original.prompt = Prompt(prompt_structure="openai", final_prompt="original", prompt_hash=hashlib.sha256(b"original").hexdigest())
    test_db.commit()
    retried = retry_run(test_db, original.id)
    assert retried.id != original.id
    assert retried.run_number == original.run_number + 1
    assert retried.status == "pending"
    assert (
        retried.input_tokens,
        retried.output_tokens,
        retried.total_tokens,
        retried.model_call_count,
    ) == (0, 0, 0, 0)
    test_db.refresh(original)
    assert original.status == "complete"
    assert original.prompt.prompt_hash == hashlib.sha256(b"original").hexdigest()
    assert retried.model_settings == original.model_settings


def test_run_without_overrides_persists_effective_environment_settings(
    test_db, monkeypatch
):
    item = condition(test_db)
    monkeypatch.setattr(settings, "llm_provider", "google")
    monkeypatch.setattr(settings, "llm_model", "gemini-environment")
    monkeypatch.setattr(settings, "llm_temperature", 0.31)
    monkeypatch.setattr(settings, "llm_top_p", 0.82)
    monkeypatch.setattr(settings, "llm_max_output_tokens", 4096)
    monkeypatch.setattr(settings, "llm_reasoning_effort", "high")

    run = create_run(test_db, item.id, [])

    assert run.execution_config == {
        "schema_version": "1",
        "requested": {},
        "effective": {
            "provider": "google",
            "model": "gemini-environment",
            "temperature": 0.31,
            "top_p": 0.82,
            "seed": None,
            "max_output_tokens": 4096,
            "reasoning_effort": "high",
            "provider_settings": {},
        },
        "effective_provider_request": {
            "provider": "google",
            "model": "gemini-environment",
            "temperature": 0.31,
            "top_p": 0.82,
            "max_output_tokens": 4096,
        },
    }
    assert run.provider == "google"
    assert run.model == "gemini-environment"
    assert run.temperature == 0.31
    assert run.top_p == 0.82
    assert run.max_tokens == 4096


def test_run_snapshot_uses_openai_sol_defaults(test_db, monkeypatch):
    item = condition(test_db)
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_model", "gpt-5.6-sol")

    run = create_run(test_db, item.id, [])

    assert run.provider == "openai"
    assert run.model == "gpt-5.6-sol"
    assert run.execution_config["effective_provider_request"]["provider"] == "openai"
    assert run.execution_config["effective_provider_request"]["model"] == "gpt-5.6-sol"


def test_retry_copies_effective_snapshot_when_environment_defaults_change(
    test_db, monkeypatch
):
    item = condition(test_db)
    monkeypatch.setattr(settings, "llm_model", "gemini-original")
    original = create_run(test_db, item.id, [])
    monkeypatch.setattr(settings, "llm_model", "gemini-new-default")

    retried = retry_run(test_db, original.id)

    assert retried.execution_config == original.execution_config
    assert retried.model == "gemini-original"


def test_retry_copies_source_binding_snapshot(test_db):
    item = condition(test_db)
    source = SourceDocument(name="S", document_type="reference", version="1", original_filename="s.txt", media_type="text/plain", content=b"hello", content_hash=hashlib.sha256(b"hello").hexdigest(), extracted_text="hello")
    test_db.add(source); test_db.flush()
    original = create_run(test_db, item.id, [SourceBinding(source_document_id=source.id, role="reference_content", ordinal=0)])
    original_hash = original.source_documents[0].included_text_hash
    source.extracted_text = "changed after the original snapshot"
    test_db.commit()
    retried = retry_run(test_db, original.id)
    assert [(b.source_document_id, b.role, b.ordinal, b.included_text_hash) for b in retried.source_documents] == [(source.id, "reference_content", 0, original_hash)]


def test_pdf_backed_retry_requires_fresh_filename_metadata(test_db):
    item = condition(test_db)
    original = create_run(test_db, item.id, [])
    original.reference_pdfs = [
        RunReferencePdf(ordinal=0, original_filename="old.pdf")
    ]
    test_db.commit()

    with pytest.raises(HTTPException) as raised:
        retry_run(test_db, original.id)

    assert raised.value.status_code == 409
    assert raised.value.detail["code"] == "reference_pdfs_required"


def test_pdf_backed_retry_uses_new_ordered_names_without_mutating_original(
    test_db,
):
    item = condition(test_db)
    original = create_run(
        test_db,
        item.id,
        [],
        ModelSettings(model="gemini-test", temperature=0.2),
    )
    original.reference_pdfs = [
        RunReferencePdf(ordinal=0, original_filename="old.pdf")
    ]
    test_db.commit()

    retried = retry_run(
        test_db,
        original.id,
        ["new-one.pdf", "new-two.pdf"],
    )

    assert retried.reference_pdf_filenames == ["new-one.pdf", "new-two.pdf"]
    assert retried.model_settings == original.model_settings
    test_db.refresh(original)
    assert original.reference_pdf_filenames == ["old.pdf"]


def test_non_pdf_retry_rejects_supplied_filename_metadata(test_db):
    item = condition(test_db)
    original = create_run(test_db, item.id, [])

    with pytest.raises(HTTPException) as raised:
        retry_run(test_db, original.id, ["unexpected.pdf"])

    assert raised.value.status_code == 409
    assert raised.value.detail["code"] == "reference_pdfs_not_allowed"


def test_public_binding_always_hashes_persisted_extracted_text(test_db):
    item = condition(test_db)
    source = SourceDocument(name="S2", document_type="reference", version="1", original_filename="s2.txt", media_type="text/plain", content=b"different bytes", content_hash=hashlib.sha256(b"different bytes").hexdigest(), extracted_text="trusted extracted text")
    test_db.add(source); test_db.flush()
    run = create_run(test_db, item.id, [SourceBinding(source_document_id=source.id, role="reference_content", ordinal=0)])
    assert run.source_documents[0].included_text_hash == hashlib.sha256(b"trusted extracted text").hexdigest()


def test_create_rejects_duplicate_role_ordinal(test_db):
    item = condition(test_db)
    bindings = [SourceBinding(source_document_id=1, role="rubric", ordinal=0), SourceBinding(source_document_id=2, role="rubric", ordinal=0)]
    with pytest.raises(ValueError, match="Duplicate"):
        create_run(test_db, item.id, bindings)


def test_missing_source_rolls_back_insert_and_leaves_session_usable(test_db):
    item = condition(test_db)
    test_db.commit()
    with pytest.raises(Exception):
        create_run(test_db, item.id, [SourceBinding(source_document_id=999, role="rubric", ordinal=0)])
    assert test_db.query(Run).filter_by(condition_id=item.id).count() == 0
    assert create_run(test_db, item.id, []).run_number == 1


def test_integrity_retry_preserves_flushed_parent_objects(test_db):
    item = condition(test_db)
    parent_id = item.experiment_id
    raised = False

    def fail_first_run_flush(session, flush_context, instances):
        nonlocal raised
        if not raised and any(isinstance(value, Run) for value in session.new):
            raised = True
            raise IntegrityError("insert run", {}, Exception("simulated conflict"))

    event.listen(test_db, "before_flush", fail_first_run_flush)
    try:
        run = create_run(test_db, item.id, [])
    finally:
        event.remove(test_db, "before_flush", fail_first_run_flush)
    assert raised
    assert run.run_number == 1
    assert test_db.get(Experiment, parent_id) is not None
    assert test_db.get(Condition, item.id) is not None


def test_evaluation_retry_reuses_saved_run_and_enqueues_only_evaluation(test_db):
    item = condition(test_db)
    run = create_run(test_db, item.id, [])
    run.status = "complete"
    run.viewer_ready_at = run.created_at
    run.completed_at = run.created_at
    run.progress_message = "Complete"
    run.assessment = Assessment(
        raw_response_text='{"questions": [{"body": "Saved"}]}',
        parsed_json={"questions": [{"body": "Saved"}]},
        output_hash="a" * 64,
        schema_version="1",
    )
    run.document_artifact = DocumentArtifact(
        filename="saved.docx",
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        content=b"docx",
    )
    test_db.commit()
    persist_assessment_questions(test_db, run.assessment)
    test_db.commit()
    assessment_id = run.assessment.id

    with patch(
        "backend.workers.evaluation_worker.run_llm_evaluation_pipeline.delay"
    ) as evaluation_delay:
        retried = retry_llm_evaluation(test_db, assessment_id)

    assert retried.id == run.id
    assert retried.assessment.id == assessment_id
    assert retried.status == "complete"
    assert retried.completed_at == retried.created_at
    assert retried.progress_message == "Complete"
    assert retried.error_type is None
    assert retried.error_message is None
    evaluation_delay.assert_called_once_with(run.id)
