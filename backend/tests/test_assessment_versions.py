import hashlib

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.models.experiment import Condition, Experiment
from backend.models.docx_authoring import DocxAuthoringAttempt
from backend.models.run import Assessment, DocumentArtifact, Run


def saved_run(db, *, run_number=1):
    experiment = Experiment(
        course="C",
        topic="T",
        learning_objectives=["L"],
        assessment_type="mixed",
        difficulty="D",
        number_of_questions=1,
    )
    condition = Condition(
        experiment=experiment,
        prompt_structure="openai",
        factor_inputs={},
        condition_label="test",
    )
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=run_number,
        execution_config={},
    )
    db.add(run)
    db.flush()
    return run


def assessment(version=1, kind="original_generation"):
    raw = f'{{"version": {version}}}'
    return Assessment(
        version=version,
        kind=kind,
        raw_response_text=raw,
        parsed_json={"questions": []},
        output_hash=hashlib.sha256(raw.encode()).hexdigest(),
        schema_version="2",
    )


def artifact(content=b"docx"):
    return DocumentArtifact(
        filename="assessment.docx",
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        content=content,
    )


def test_run_tracks_explicit_canonical_assessment_version(test_db):
    run = saved_run(test_db)
    original = assessment()
    run.assessment_versions.append(original)
    run.canonical_assessment = original
    original.document_artifact = artifact()
    test_db.commit()

    assert run.canonical_assessment_id == original.id
    assert run.assessment is original
    assert run.document_artifact is original.document_artifact
    assert original.kind == "original_generation"
    assert original.version == 1


def test_assessment_versions_are_unique_within_a_run(test_db):
    run = saved_run(test_db)
    run.assessment_versions.extend([assessment(), assessment()])

    with pytest.raises(IntegrityError):
        test_db.commit()


def test_artifact_and_canonical_assessment_must_belong_to_same_run(test_db):
    test_db.execute(text("PRAGMA foreign_keys=ON"))
    first = saved_run(test_db, run_number=1)
    second = saved_run(test_db, run_number=2)
    first_assessment = assessment()
    second_assessment = assessment()
    first.assessment_versions.append(first_assessment)
    second.assessment_versions.append(second_assessment)
    first.canonical_assessment = second_assessment

    with pytest.raises(IntegrityError):
        test_db.commit()


def authoring_attempt(run, source, **overrides):
    values = {
        "run_id": run.id,
        "source_assessment_id": source.id,
        "cycle_number": 1,
        "attempt_number": 1,
        "status": "generated",
        "provider": "google",
        "model": "gemini-3.5-flash-lite",
        "model_version": "2026-08-01",
        "provider_request_id": "request-1",
        "prompt_hash": "a" * 64,
        "grounding_hash": "b" * 64,
        "idempotency_key": "cycle-one",
        "program_text": "from docx import Document",
        "envelope": {"language": "python"},
        "sandbox_image_digest": "c" * 64,
        "execution_report": {"exit_code": 0},
        "validation_report": {"valid": True},
    }
    values.update(overrides)
    return DocxAuthoringAttempt(**values)


def test_docx_authoring_attempt_preserves_program_and_validation_evidence(test_db):
    run = saved_run(test_db)
    source = assessment()
    run.assessment = source
    test_db.commit()

    attempt = authoring_attempt(run, source)
    test_db.add(attempt)
    test_db.commit()

    assert attempt.source_assessment is source
    assert attempt.program_text == "from docx import Document"
    assert attempt.envelope == {"language": "python"}
    assert attempt.execution_report == {"exit_code": 0}
    assert attempt.validation_report == {"valid": True}
    assert attempt.run is run


@pytest.mark.parametrize(
    "overrides",
    [
        {"attempt_number": 3},
        {"cycle_number": 0},
        {"failure_category": "security_violation", "repairable": True},
        {"failure_category": "hostile_code", "repairable": True},
        {"attempt_number": 2, "idempotency_key": "repair-key"},
    ],
)
def test_docx_authoring_attempt_rejects_invalid_lifecycle_state(test_db, overrides):
    run = saved_run(test_db)
    source = assessment()
    run.assessment = source
    test_db.commit()
    test_db.add(authoring_attempt(run, source, **overrides))

    with pytest.raises(IntegrityError):
        test_db.commit()


def test_docx_authoring_attempt_cycle_and_idempotency_are_unique(test_db):
    run = saved_run(test_db)
    source = assessment()
    run.assessment = source
    test_db.commit()
    test_db.add_all(
        [
            authoring_attempt(run, source),
            authoring_attempt(run, source, provider_request_id="request-2"),
        ]
    )

    with pytest.raises(IntegrityError):
        test_db.commit()
