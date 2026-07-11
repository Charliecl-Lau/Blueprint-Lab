from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.experiment import DocumentArtifact, Generation
from backend.api.runs import run_detail
from backend.services.run_service import retry_run
from backend.workers.assessment_worker import run_generation_pipeline


router = APIRouter(prefix="/generations", tags=["generations"])


@router.get("/{generation_id}")
def get_generation(generation_id: int, db: Session = Depends(get_db)):
    generation = db.get(Generation, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    result = run_detail(generation)
    result.update({"generation_id": generation.id, "prompt_text": generation.prompt.full_prompt if generation.prompt else None, "condition": generation.condition, "generated_json": generation.generated_json, "model_name": generation.model_name, "model_version": generation.model_version, "generation_time_ms": generation.generation_time_ms})
    return result


@router.post("/{generation_id}/regenerate")
def regenerate_generation(generation_id: int, response: Response, db: Session = Depends(get_db)):
    generation = db.get(Generation, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Generation not found")

    run = retry_run(db, generation.id)
    run_generation_pipeline.delay(run.id)
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'</runs/{generation_id}/retry>; rel="successor-version"'
    return {"run_id": run.id, "generation_id": run.id, "status": "pending"}


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
