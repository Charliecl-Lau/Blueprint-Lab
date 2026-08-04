from __future__ import annotations

import hashlib
import subprocess
import tempfile
import time
from pathlib import Path

from pypdf import PdfReader

from backend.config import settings
from backend.services.docx_verification import VerificationIssue, VerificationReport


class DocxRenderVerifier:
    def __init__(self, *, runner=subprocess.run):
        self.runner = runner

    def verify(self, docx_bytes: bytes) -> VerificationReport:
        started = time.perf_counter()
        issues: list[VerificationIssue] = []
        page_count = None
        version = "unavailable"
        try:
            version_result = self.runner(
                [settings.docx_render_command, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            version = (version_result.stdout or version_result.stderr).strip()[:200]
            if settings.docx_render_expected_version and settings.docx_render_expected_version not in version:
                issues.append(VerificationIssue("render_version_mismatch", repairable=False, evidence="LibreOffice version does not match the pinned version"))
            with tempfile.TemporaryDirectory(prefix="docx-render-") as root:
                source = Path(root) / "assessment.docx"
                source.write_bytes(docx_bytes)
                result = self.runner(
                    [settings.docx_render_command, "--headless", "--convert-to", "pdf", "--outdir", root, str(source)],
                    capture_output=True,
                    text=True,
                    timeout=settings.docx_render_timeout_seconds,
                    check=False,
                )
                pdf_path = Path(root) / "assessment.pdf"
                if result.returncode != 0 or not pdf_path.exists():
                    raise RuntimeError("conversion did not produce a PDF")
                reader = PdfReader(str(pdf_path))
                page_count = len(reader.pages)
                if not settings.docx_render_min_pages <= page_count <= settings.docx_render_max_pages:
                    issues.append(VerificationIssue("render_page_count", evidence=f"rendered {page_count} pages"))
                for index, page in enumerate(reader.pages):
                    text = (page.extract_text() or "").strip()
                    contents = page.get_contents()
                    content_bytes = contents.get_data() if contents is not None else b""
                    if not text and not content_bytes.strip():
                        issues.append(VerificationIssue("render_empty_page", evidence=f"page {index + 1} is empty"))
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
            issues.append(VerificationIssue("render_failed", evidence=f"{type(exc).__name__}: {str(exc)[:300]}"))
        return VerificationReport(
            valid=not issues,
            issues=tuple(issues),
            package_sha256=hashlib.sha256(docx_bytes).hexdigest(),
            rendered_page_count=page_count,
            tool_versions={"libreoffice": version, "render_verifier": "1"},
            render_duration_ms=int((time.perf_counter() - started) * 1000),
        )
