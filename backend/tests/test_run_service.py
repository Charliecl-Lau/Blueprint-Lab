import hashlib

import pytest

from backend.models.experiment import Condition, Experiment
from backend.models.run import Prompt, Run
from backend.models.source_document import SourceDocument
from backend.schemas.run_schema import ModelSettings, SourceBinding
from backend.services.run_service import create_run, retry_run


def condition(db):
    experiment = Experiment(course="C", topic="T", learning_objectives="L", assessment_type="mixed", difficulty="D", number_of_questions=1)
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
    test_db.refresh(original)
    assert original.status == "complete"
    assert original.prompt.prompt_hash == hashlib.sha256(b"original").hexdigest()
    assert retried.model_settings == original.model_settings


def test_retry_copies_source_binding_snapshot(test_db):
    item = condition(test_db)
    source = SourceDocument(name="S", document_type="reference", version="1", original_filename="s.txt", media_type="text/plain", content=b"hello", content_hash=hashlib.sha256(b"hello").hexdigest(), extracted_text="hello")
    test_db.add(source); test_db.flush()
    original = create_run(test_db, item.id, [SourceBinding(source_document_id=source.id, role="reference_content", ordinal=0)])
    retried = retry_run(test_db, original.id)
    assert [(b.source_document_id, b.role, b.ordinal, b.included_text_hash) for b in retried.source_documents] == [(source.id, "reference_content", 0, hashlib.sha256(b"hello").hexdigest())]


def test_create_rejects_duplicate_role_ordinal(test_db):
    item = condition(test_db)
    bindings = [SourceBinding(source_document_id=1, role="rubric", ordinal=0), SourceBinding(source_document_id=2, role="rubric", ordinal=0)]
    with pytest.raises(ValueError, match="Duplicate"):
        create_run(test_db, item.id, bindings)
