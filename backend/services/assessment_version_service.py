from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.experiment import utc_now
from backend.models.run import Assessment, DocumentArtifact, Run
from backend.services.assessment_evaluation import persist_assessment_questions
from backend.services.reproducibility import canonical_json, sha256_bytes, sha256_text


class AssessmentVersionConflict(RuntimeError):
    """Raised when a version request conflicts with immutable saved evidence."""


@dataclass(frozen=True)
class _PreparedAssessment:
    manifest: dict
    raw_response_text: str
    output_hash: str
    parsed_json_hash: str


def _prepare(manifest: dict, raw_response_text: str | None) -> _PreparedAssessment:
    copied = deepcopy(manifest)
    if not isinstance(copied, dict) or not isinstance(copied.get("questions"), list):
        raise ValueError("validated assessment manifest must contain a questions array")
    canonical = canonical_json(copied)
    raw = raw_response_text if raw_response_text is not None else canonical
    return _PreparedAssessment(
        manifest=copied,
        raw_response_text=raw,
        output_hash=sha256_text(raw),
        parsed_json_hash=sha256_text(canonical),
    )


def _versions(db: Session, run_id: int) -> list[Assessment]:
    return list(
        db.scalars(
            select(Assessment)
            .where(Assessment.run_id == run_id)
            .order_by(Assessment.version)
        )
    )


def _require_contiguous(versions: list[Assessment]) -> None:
    actual = [item.version for item in versions]
    if actual != list(range(1, len(actual) + 1)):
        raise AssessmentVersionConflict("assessment version gaps are not permitted")


def _same_assessment(existing: Assessment, prepared: _PreparedAssessment) -> bool:
    return (
        existing.output_hash == prepared.output_hash
        and existing.parsed_json_hash == prepared.parsed_json_hash
    )


def persist_original_version(
    db: Session,
    *,
    run: Run,
    manifest: dict,
    raw_response_text: str | None = None,
    schema_version: str = "2",
) -> Assessment:
    prepared = _prepare(manifest, raw_response_text)
    versions = _versions(db, run.id)
    _require_contiguous(versions)
    if versions:
        original = versions[0]
        if (
            len(versions) == 1
            and original.version == 1
            and original.kind == "original_generation"
            and _same_assessment(original, prepared)
        ):
            return original
        raise AssessmentVersionConflict("run already has immutable assessment evidence")

    try:
        with db.begin_nested():
            original = Assessment(
                run=run,
                version=1,
                kind="original_generation",
                raw_response_text=prepared.raw_response_text,
                parsed_json=prepared.manifest,
                output_hash=prepared.output_hash,
                parsed_json_hash=prepared.parsed_json_hash,
                schema_version=schema_version,
                validation_status="valid",
                canonicalized_at=utc_now(),
            )
            db.add(original)
            db.flush()
            persist_assessment_questions(db, original)
            run.canonical_assessment = original
            db.flush()
        db.commit()
        db.refresh(original)
        return original
    except Exception:
        db.rollback()
        raise


def persist_rewrite_and_canonicalize(
    db: Session,
    *,
    run: Run,
    manifest: dict,
    artifact: DocumentArtifact,
    raw_response_text: str | None = None,
    schema_version: str = "2",
) -> Assessment:
    prepared = _prepare(manifest, raw_response_text)
    artifact_hash = sha256_bytes(bytes(artifact.content))
    versions = _versions(db, run.id)
    _require_contiguous(versions)
    if not versions or versions[0].version != 1:
        raise AssessmentVersionConflict("rewrite requires version 1 of the same run")
    original = versions[0]
    if original.kind != "original_generation" or original.run_id != run.id:
        raise AssessmentVersionConflict("rewrite source must be the run's original version")

    if len(versions) > 1:
        existing = versions[1]
        existing_artifact = existing.document_artifact
        if (
            len(versions) == 2
            and existing.version == 2
            and existing.kind == "full_rewrite"
            and existing.source_assessment_id == original.id
            and _same_assessment(existing, prepared)
            and existing_artifact is not None
            and existing_artifact.content_hash == artifact_hash
        ):
            return existing
        raise AssessmentVersionConflict(
            "canonical rewrite already exists with different evidence"
        )
    if run.canonical_assessment_id != original.id:
        raise AssessmentVersionConflict(
            "first rewrite must source the canonical original assessment"
        )

    try:
        with db.begin_nested():
            rewrite = Assessment(
                run=run,
                version=2,
                kind="full_rewrite",
                source_assessment_id=original.id,
                raw_response_text=prepared.raw_response_text,
                parsed_json=prepared.manifest,
                output_hash=prepared.output_hash,
                parsed_json_hash=prepared.parsed_json_hash,
                schema_version=schema_version,
                validation_status="valid",
                canonicalized_at=utc_now(),
            )
            db.add(rewrite)
            db.flush()
            persist_assessment_questions(db, rewrite)
            artifact.run_id = run.id
            artifact.assessment = rewrite
            artifact.content_hash = artifact_hash
            db.add(artifact)
            run.canonical_assessment = rewrite
            db.flush()
        db.commit()
        db.refresh(rewrite)
        return rewrite
    except Exception:
        db.rollback()
        raise
