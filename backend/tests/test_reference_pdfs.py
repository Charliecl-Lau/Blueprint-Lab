import logging
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from starlette.datastructures import Headers, UploadFile

from backend.services.reference_pdfs import (
    MAX_REFERENCE_PDF_BYTES,
    ProviderFileAttachment,
    ReferencePdfValidationError,
    delete_provider_attachments,
    read_reference_pdfs,
)


def upload(
    name: str,
    content: bytes = b"%PDF-1.7\nvalid",
    media_type: str = "application/pdf",
) -> UploadFile:
    return UploadFile(
        filename=name,
        file=BytesIO(content),
        headers=Headers({"content-type": media_type}),
    )


@pytest.mark.asyncio
async def test_reads_three_pdfs_in_order_and_sanitizes_names():
    files = [
        upload("one.pdf"),
        upload("folder/two.pdf"),
        upload("three.pdf"),
    ]

    result = await read_reference_pdfs(files)

    assert [item.filename for item in result] == [
        "one.pdf",
        "two.pdf",
        "three.pdf",
    ]
    assert result[0].content == b"%PDF-1.7\nvalid"


@pytest.mark.asyncio
async def test_rejects_empty_pdf_list():
    with pytest.raises(ReferencePdfValidationError) as raised:
        await read_reference_pdfs([])

    assert raised.value.code == "reference_pdfs_required"


@pytest.mark.asyncio
async def test_rejects_more_than_three_pdfs_before_reading():
    files = [upload(f"{index}.pdf") for index in range(4)]

    with pytest.raises(ReferencePdfValidationError) as raised:
        await read_reference_pdfs(files)

    assert raised.value.code == "too_many_reference_pdfs"


@pytest.mark.asyncio
async def test_rejects_each_pdf_over_20_mb():
    oversized = b"%PDF-1.7\n" + b"x" * MAX_REFERENCE_PDF_BYTES

    with pytest.raises(ReferencePdfValidationError) as raised:
        await read_reference_pdfs([upload("large.pdf", oversized)])

    assert raised.value.code == "reference_pdf_too_large"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "media_type", "code"),
    [
        ("reference.txt", "application/pdf", "invalid_reference_pdf_extension"),
        ("reference.pdf", "text/plain", "invalid_reference_pdf_mime_type"),
        ("   ", "application/pdf", "invalid_reference_pdf_filename"),
    ],
)
async def test_rejects_invalid_pdf_metadata(name, media_type, code):
    with pytest.raises(ReferencePdfValidationError) as raised:
        await read_reference_pdfs([upload(name, media_type=media_type)])

    assert raised.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"", "empty_reference_pdf"),
        (b"not a pdf", "invalid_reference_pdf_signature"),
    ],
)
async def test_rejects_invalid_pdf_content(content, code):
    with pytest.raises(ReferencePdfValidationError) as raised:
        await read_reference_pdfs([upload("reference.pdf", content)])

    assert raised.value.code == code


def test_provider_attachment_round_trips_through_task_metadata():
    attachment = ProviderFileAttachment(
        name="files/reference-1",
        uri="https://files/reference-1",
        mime_type="application/pdf",
    )

    assert ProviderFileAttachment.from_dict(attachment.to_dict()) == attachment


def test_cleanup_logs_deletion_failures_without_provider_details(caplog):
    llm = MagicMock()
    llm.delete_file.side_effect = RuntimeError("provider URI secret-value")
    attachment = ProviderFileAttachment(
        name="files/private-provider-id",
        uri="https://provider/private-uri",
        mime_type="application/pdf",
    )

    with caplog.at_level(logging.WARNING):
        delete_provider_attachments(llm, [attachment])

    assert "Reference PDF provider cleanup failed" in caplog.text
    assert "secret-value" not in caplog.text
    assert "private-provider-id" not in caplog.text


def test_cleanup_treats_provider_not_found_as_success(caplog):
    llm = MagicMock()
    error = RuntimeError("provider detail")
    error.status_code = 404
    llm.delete_file.side_effect = error

    with caplog.at_level(logging.WARNING):
        delete_provider_attachments(llm, [
            ProviderFileAttachment(
                name="files/already-deleted",
                uri="https://provider/already-deleted",
                mime_type="application/pdf",
            )
        ])

    assert "Reference PDF provider cleanup failed" not in caplog.text
