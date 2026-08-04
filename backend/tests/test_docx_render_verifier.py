import subprocess

from backend.services.docx_render_verifier import DocxRenderVerifier


def test_render_verifier_reports_conversion_failure_without_repairing():
    def missing(*args, **kwargs):
        raise FileNotFoundError("libreoffice unavailable")
    report = DocxRenderVerifier(runner=missing).verify(b"docx")
    assert not report.valid
    assert report.issues[0].code == "render_failed"
