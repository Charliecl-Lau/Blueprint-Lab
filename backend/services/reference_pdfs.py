from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile


MAX_REFERENCE_PDFS = 3
MAX_REFERENCE_PDF_BYTES = 20 * 1024 * 1024
_READ_CHUNK_BYTES = 1024 * 1024


class ReferencePdfValidationError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ValidatedReferencePdf:
    filename: str
    content: bytes


@dataclass(frozen=True)
class ProviderFileAttachment:
    name: str
    uri: str
    mime_type: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "uri": self.uri,
            "mime_type": self.mime_type,
        }

    @classmethod
    def from_dict(cls, value: dict[str, str]) -> "ProviderFileAttachment":
        return cls(
            name=value["name"],
            uri=value["uri"],
            mime_type=value["mime_type"],
        )


def delete_provider_attachments(llm, attachments) -> None:
    for attachment in reversed(attachments):
        try:
            llm.delete_file(attachment.name)
        except Exception:
            continue


def upload_provider_attachments(
    llm,
    pdfs: list[ValidatedReferencePdf],
) -> list[ProviderFileAttachment]:
    attachments = []
    try:
        for pdf in pdfs:
            attachments.append(llm.upload_pdf(pdf))
    except Exception:
        delete_provider_attachments(llm, attachments)
        raise
    return attachments


async def read_reference_pdfs(
    files: list[UploadFile],
) -> list[ValidatedReferencePdf]:
    if not files:
        raise ReferencePdfValidationError(
            "reference_pdfs_required",
            "At least one reference PDF is required.",
        )
    if len(files) > MAX_REFERENCE_PDFS:
        raise ReferencePdfValidationError(
            "too_many_reference_pdfs",
            f"No more than {MAX_REFERENCE_PDFS} reference PDFs are allowed.",
        )

    validated = []
    for upload in files:
        filename = Path(upload.filename or "").name.strip()
        if not filename:
            raise ReferencePdfValidationError(
                "invalid_reference_pdf_filename",
                "Each reference PDF must have a filename.",
            )
        if Path(filename).suffix.lower() != ".pdf":
            raise ReferencePdfValidationError(
                "invalid_reference_pdf_extension",
                f"Reference file '{filename}' must use the .pdf extension.",
            )
        if upload.content_type != "application/pdf":
            raise ReferencePdfValidationError(
                "invalid_reference_pdf_mime_type",
                f"Reference file '{filename}' must have application/pdf content type.",
            )

        chunks = []
        total_bytes = 0
        while True:
            chunk = await upload.read(_READ_CHUNK_BYTES)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_REFERENCE_PDF_BYTES:
                raise ReferencePdfValidationError(
                    "reference_pdf_too_large",
                    f"Reference file '{filename}' exceeds 20 MB.",
                )
            chunks.append(chunk)

        content = b"".join(chunks)
        if not content:
            raise ReferencePdfValidationError(
                "empty_reference_pdf",
                f"Reference file '{filename}' is empty.",
            )
        if not content.startswith(b"%PDF-"):
            raise ReferencePdfValidationError(
                "invalid_reference_pdf_signature",
                f"Reference file '{filename}' is not a valid PDF.",
            )
        validated.append(ValidatedReferencePdf(filename=filename, content=content))

    return validated
