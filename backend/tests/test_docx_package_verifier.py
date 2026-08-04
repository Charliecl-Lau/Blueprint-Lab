from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document

from backend.services.docx_package_verifier import DocxPackageVerifier


CONTENT_TYPES = b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
RELS = b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'


def package(extra=None):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", RELS)
        archive.writestr("word/document.xml", b"<document/>")
        if extra: archive.writestr(*extra)
    return output.getvalue()


def test_package_verifier_accepts_minimal_safe_ooxml():
    assert DocxPackageVerifier().verify(package()).valid


def test_package_verifier_accepts_standard_python_docx_custom_xml_parts():
    output = BytesIO()
    Document().save(output)

    assert DocxPackageVerifier().verify(output.getvalue()).valid


def test_package_verifier_rejects_macros_and_external_relationships():
    report = DocxPackageVerifier().verify(package(("word/vbaProject.bin", b"bad")))
    assert not report.valid
    assert any(not issue.repairable for issue in report.issues)
