from sqlalchemy.orm import Session

from backend.models import DocumentArtifact, Run
from backend.services.assessment_evaluation import EvaluationValidationError
from backend.services.docx_exporter import build_assessment_docx
from backend.services.reproducibility import sha256_bytes


DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def save_assessment_artifact(db: Session, run: Run) -> DocumentArtifact:
    if run.document_artifact is not None:
        return run.document_artifact
    assessment = run.assessment
    if assessment is None or assessment.parsed_json is None:
        raise EvaluationValidationError("saved assessment is unavailable")
    if run.prompt is None:
        raise EvaluationValidationError("saved assessment prompt is unavailable")

    docx_bytes = build_assessment_docx(
        run_id=run.id,
        prompt_id=run.prompt.id,
        condition_code=run.condition.condition_code,
        run_number=run.run_number,
        course=run.experiment.course,
        topic=run.experiment.topic,
        questions=assessment.parsed_json["questions"],
    )
    artifact = DocumentArtifact(
        run_id=run.id,
        filename=f"blueprint-lab-run-{run.id}.docx",
        media_type=DOCX_MEDIA_TYPE,
        content=docx_bytes,
        content_hash=sha256_bytes(docx_bytes),
    )
    db.add(artifact)
    return artifact
