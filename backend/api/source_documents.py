from __future__ import annotations

from typing import Optional
from urllib.parse import quote
import re
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.source_document import SourceDocument
from backend.schemas.source_document_schema import SourceDocumentResponse
from backend.services.source_documents import MAX_SOURCE_DOCUMENT_BYTES, SourceDocumentValidationError, create_source_document

router = APIRouter(prefix="/source-documents", tags=["source-documents"])


@router.post("", response_model=SourceDocumentResponse, status_code=201)
async def upload_source_document(name: str = Form(...), document_type: str = Form(...),
        version: str = Form(...), description: Optional[str] = Form(None), file: UploadFile = File(...),
        db: Session = Depends(get_db)):
    try:
        chunks = []
        total = 0
        while True:
            chunk = await file.read(min(1024 * 1024, MAX_SOURCE_DOCUMENT_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_SOURCE_DOCUMENT_BYTES:
                raise SourceDocumentValidationError("source_document_too_large")
        content = b"".join(chunks)
        return create_source_document(db, name=name, document_type=document_type, version=version,
            filename=file.filename or "upload", media_type=file.content_type or "application/octet-stream",
            content=content, description=description)
    except SourceDocumentValidationError as exc:
        raise HTTPException(422, detail={"code": exc.code}) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail={"code": "duplicate_source_version"}) from exc
    finally:
        await file.close()


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
    clean = "".join(character for character in source.original_filename
        if ord(character) >= 32 and ord(character) != 127 and character not in '\r\n')
    ascii_name = "".join(character if 32 <= ord(character) < 127 and character not in '"\\' else "_"
        for character in clean) or "download"
    ascii_name = re.sub(r"%0[ad]", "_", ascii_name, flags=re.IGNORECASE)
    disposition = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(clean, safe="")}'
    return Response(source.content, media_type=source.media_type,
        headers={"Content-Disposition": disposition})
