from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.experiment import DocumentArtifact, Generation
from backend.schemas.experiment_schema import GenerationDetailResponse
from backend.workers.assessment_worker import run_generation_pipeline


router = APIRouter(prefix="/generations", tags=["generations"])


@router.get("/{generation_id}", response_model=GenerationDetailResponse)
def get_generation(generation_id: int, db: Session = Depends(get_db)):
    generation = db.get(Generation, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    return GenerationDetailResponse(
        id=generation.id,
        condition_id=generation.condition_id,
        status=generation.status,
        model_name=generation.model_name,
        model_version=generation.model_version,
        generation_time_ms=generation.generation_time_ms,
        generated_json=generation.generated_json,
        condition=generation.condition,
        prompt_text=(
            generation.prompt_record.full_prompt if generation.prompt_record else None
        ),
    )


@router.post("/{generation_id}/regenerate")
def regenerate_generation(generation_id: int, db: Session = Depends(get_db)):
    generation = db.get(Generation, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Generation not found")

    if generation.prompt_record:
        db.delete(generation.prompt_record)
    if generation.document_artifact:
        db.delete(generation.document_artifact)
    generation.generated_json = None
    generation.model_name = None
    generation.model_version = None
    generation.generation_time_ms = None
    generation.completed_at = None
    generation.status = "pending"
    db.commit()

    run_generation_pipeline.delay(generation.id)
    return {"generation_id": generation.id, "status": "pending"}


@router.get("/{generation_id}/export-docx")
def export_docx(generation_id: int, db: Session = Depends(get_db)):
    artifact = db.query(DocumentArtifact).filter_by(generation_id=generation_id).first()
    if artifact is None:
        raise HTTPException(status_code=404, detail="DOCX artifact not found")
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )
