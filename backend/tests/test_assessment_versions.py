import hashlib

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.models.experiment import Condition, Experiment
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
