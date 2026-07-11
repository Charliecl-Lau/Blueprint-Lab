from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.source_document import SourceDocument
from backend.schemas.source_document_schema import SourceDocumentResponse
from backend.services.source_documents import SourceDocumentValidationError, create_source_document

router = APIRouter(prefix="/source-documents", tags=["source-documents"])


@router.post("", response_model=SourceDocumentResponse, status_code=201)
async def upload_source_document(name: str = Form(...), document_type: str = Form(...),
        version: str = Form(...), description: Optional[str] = Form(None), file: UploadFile = File(...),
        db: Session = Depends(get_db)):
    content = await file.read()
    content_hash = __import__("hashlib").sha256(content).hexdigest()
    duplicate = db.scalar(select(SourceDocument).where(
        SourceDocument.name == name, SourceDocument.document_type == document_type,
        SourceDocument.version == version, SourceDocument.original_filename == (file.filename or "upload"),
        SourceDocument.media_type == (file.content_type or "application/octet-stream"),
        SourceDocument.content_hash == content_hash, SourceDocument.description == description))
    if duplicate:
        raise HTTPException(409, detail={"code": "duplicate_source_version"})
    try:
        return create_source_document(db, name=name, document_type=document_type, version=version,
            filename=file.filename or "upload", media_type=file.content_type or "application/octet-stream",
            content=content, description=description)
    except SourceDocumentValidationError as exc:
        raise HTTPException(422, detail={"code": exc.code}) from exc


def _get(source_id: int, db: Session):
    source = db.get(SourceDocument, source_id)
    if source is None:
        raise HTTPException(404, detail={"code": "source_document_not_found"})
    return source


@router.get("/{source_id}", response_model=SourceDocumentResponse)
def get_source_document(source_id: int, db: Session = Depends(get_db)):
    return _get(source_id, db)


@router.get("/{source_id}/download")
def download_source_document(source_id: int, db: Session = Depends(get_db)):
    source = _get(source_id, db)
    return Response(source.content, media_type=source.media_type,
        headers={"Content-Disposition": f'attachment; filename="{source.original_filename}"'})
