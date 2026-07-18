from io import BytesIO

import pytest
from starlette.datastructures import Headers, UploadFile

from backend.services.reference_pdfs import (
    MAX_REFERENCE_PDF_BYTES,
    ProviderFileAttachment,
    ReferencePdfValidationError,
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
