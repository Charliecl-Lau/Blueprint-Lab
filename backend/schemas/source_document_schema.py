from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SourceDocumentResponse(BaseModel):
    id: int
    name: str
    document_type: str
    version: str
    original_filename: str
    media_type: str
    content_hash: str
    extracted_text: Optional[str]
    extraction_method: Optional[str]
    description: Optional[str]
    uploaded_at: datetime

    model_config = {"from_attributes": True}
