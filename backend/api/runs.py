from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.run import Run
from backend.schemas.run_schema import RunCreate, RunSummary
from backend.services.run_service import create_run, retry_run
from backend.workers.assessment_worker import run_generation_pipeline

router = APIRouter(tags=["runs"])

def run_detail(run: Run, include_raw_response: bool = False):
    return {"id": run.id, "experiment_id": run.experiment_id, "condition_id": run.condition_id, "run_number": run.run_number, "status": run.status, "model_settings": run.model_settings, "prompt": None if not run.prompt else {"text": run.prompt.final_prompt, "hash": run.prompt.prompt_hash, "template_version": run.prompt.template_version, "generator_version": run.prompt.generator_version}, "assessment": None if not run.assessment else {"parsed_json": run.assessment.parsed_json, "output_hash": run.assessment.output_hash, "schema_version": run.assessment.schema_version, **({"raw_response_text": run.assessment.raw_response_text} if include_raw_response else {})}, "sources": [{"source_document_id": item.source_document_id, "role": item.role, "ordinal": item.ordinal, "included_text_hash": item.included_text_hash, "name": item.source_document.name, "version": item.source_document.version} for item in run.source_documents], "error": None if not run.error_type and not run.error_message else {"type": run.error_type, "message": run.error_message}, "artifact_available": run.document_artifact is not None}

@router.post("/conditions/{condition_id}/runs", response_model=RunSummary)
def post_run(condition_id: int, payload: RunCreate, db: Session = Depends(get_db)):
    run = create_run(db, condition_id, payload.source_bindings, payload.model_settings)
    run_generation_pipeline.delay(run.id)
    return run

@router.get("/runs/{run_id}")
def get_run(run_id: int, include_raw_response: bool = False, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None: raise HTTPException(404, "Run not found")
    return run_detail(run, include_raw_response)

@router.post("/runs/{run_id}/retry", response_model=RunSummary)
def post_retry(run_id: int, db: Session = Depends(get_db)):
    run = retry_run(db, run_id); run_generation_pipeline.delay(run.id); return run

@router.get("/runs/{run_id}/export-docx")
def export_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None: raise HTTPException(404, "Run not found")
    artifact = run.document_artifact
    if artifact is None: raise HTTPException(404, "DOCX artifact not found")
    return Response(content=artifact.content, media_type=artifact.media_type, headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'})
