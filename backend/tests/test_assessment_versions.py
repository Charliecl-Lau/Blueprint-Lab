import hashlib

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.models.experiment import Condition, Experiment
from backend.models.docx_authoring import DocxAuthoringAttempt
from backend.models.evaluation import Evaluation
from backend.models.run import Assessment, DocumentArtifact, Run
from backend.services.assessment_version_service import (
    AssessmentVersionConflict,
    persist_original_version,
    persist_rewrite_and_canonicalize,
)


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


def rewrite_artifact(content=b"rewrite-docx"):
    return DocumentArtifact(
        filename="rewrite.docx",
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        content=content,
    )


def test_persist_original_version_creates_version_one_and_canonicalizes(test_db):
    run = saved_run(test_db)
    manifest = {"questions": [{"body": "Original"}]}

    original = persist_original_version(test_db, run=run, manifest=manifest)

    assert original.version == 1
    assert original.kind == "original_generation"
    assert original.parsed_json == manifest
    assert original.parsed_json_hash is not None
    assert run.canonical_assessment_id == original.id
    assert original.canonicalized_at is not None


def test_rewrite_persists_questions_artifact_and_pointer_atomically(test_db):
    run = saved_run(test_db)
    original = persist_original_version(
        test_db, run=run, manifest={"questions": [{"body": "Original"}]}
    )
    original_evaluation = Evaluation(
        experiment_id=run.experiment_id,
        condition_id=run.condition_id,
        run_id=run.id,
        assessment_id=original.id,
        question_id=original.questions[0].id,
        assessment_version=1,
        assessment_content_hash=original.questions[0].content_hash,
        evaluation_type="human",
        evaluator_identity="reviewer",
        attempt=1,
        rubric_version="1",
        rubric_snapshot={},
        prompt_design_factors={},
        major_strengths=[],
        major_weaknesses=[],
        status="finalized",
        revision=1,
    )
    test_db.add(original_evaluation)
    test_db.commit()
    rewrite = persist_rewrite_and_canonicalize(
        test_db,
        run=run,
        manifest={"questions": [{"body": "Rewritten"}]},
        artifact=rewrite_artifact(),
    )

    assert rewrite.version == 2
    assert rewrite.kind == "full_rewrite"
    assert rewrite.source_assessment_id == original.id
    assert rewrite.questions[0].assessment_version == 2
    assert rewrite.document_artifact.assessment_id == rewrite.id
    assert rewrite.document_artifact.run_id == run.id
    assert run.canonical_assessment_id == rewrite.id
    assert original.questions[0].assessment_id == original.id
    assert original_evaluation.assessment_id == original.id
    assert original_evaluation.assessment_version == 1


def test_failed_rewrite_artifact_rolls_back_version_and_pointer(test_db):
    run = saved_run(test_db)
    original = persist_original_version(
        test_db, run=run, manifest={"questions": [{"body": "Original"}]}
    )

    with pytest.raises(IntegrityError):
        persist_rewrite_and_canonicalize(
            test_db,
            run=run,
            manifest={"questions": [{"body": "Rewritten"}]},
            artifact=DocumentArtifact(
                filename=None,
                media_type="application/octet-stream",
                content=b"invalid",
            ),
        )

    test_db.refresh(run)
    assert run.canonical_assessment_id == original.id
    assert [item.version for item in run.assessment_versions] == [1]


def test_rewrite_canonicalization_is_hash_idempotent_or_conflicts(test_db):
    run = saved_run(test_db)
    persist_original_version(
        test_db, run=run, manifest={"questions": [{"body": "Original"}]}
    )
    manifest = {"questions": [{"body": "Rewritten"}]}
    first = persist_rewrite_and_canonicalize(
        test_db, run=run, manifest=manifest, artifact=rewrite_artifact()
    )

    repeated = persist_rewrite_and_canonicalize(
        test_db, run=run, manifest=manifest, artifact=rewrite_artifact()
    )
    assert repeated.id == first.id

    with pytest.raises(AssessmentVersionConflict):
        persist_rewrite_and_canonicalize(
            test_db,
            run=run,
            manifest={"questions": [{"body": "Different"}]},
            artifact=rewrite_artifact(),
        )
