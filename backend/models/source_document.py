from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.experiment import utc_now


class SourceDocument(Base):
    __tablename__ = "source_documents"
    __table_args__ = (CheckConstraint("length(content_hash) = 64"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    document_type: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text)
    extraction_method: Mapped[Optional[str]] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    runs: Mapped[list["RunSourceDocument"]] = relationship(back_populates="source_document")


class RunSourceDocument(Base):
    __tablename__ = "run_source_documents"
    __table_args__ = (
        CheckConstraint(
            "role IN ('course_syllabus','bridge_map','few_shot_example','rubric',"
            "'reference_content','instructor_example')"
        ),
        CheckConstraint("length(included_text_hash) = 64"),
        UniqueConstraint("run_id", "role", "ordinal"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    included_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    run: Mapped["Run"] = relationship(back_populates="source_documents")
    source_document: Mapped[SourceDocument] = relationship(back_populates="runs")
