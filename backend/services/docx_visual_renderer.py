"""Bounded LibreOffice/PDF rendering for multimodal review."""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PIL import Image
from pypdf import PdfReader


class DocxVisualRenderError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message); self.code = code


@dataclass(frozen=True)
class PageImage:
    page_number: int
    width: int
    height: int
    byte_size: int
    sha256: str
    temporary_handle: str
    _png_bytes: bytes = field(repr=False, compare=False)

    def inline_part(self) -> dict:
        return {"mime_type": "image/png", "data": self._png_bytes}

    def public_metadata(self) -> dict:
        return {"page_number": self.page_number, "width": self.width, "height": self.height, "byte_size": self.byte_size, "sha256": self.sha256}


@dataclass(frozen=True)
class VisualFinding:
    code: str
    severity: str
    page_number: Optional[int]
    evidence: str


class RenderedDraft:
    def __init__(self, directory: str, pdf_bytes: bytes, pages: list[PageImage], findings: list[VisualFinding], renderer_version: str):
        self._directory = directory
        self.pdf_bytes = pdf_bytes
        self.pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        self.pages = tuple(pages)
        self.findings = tuple(findings)
        self.renderer_version = renderer_version

    def close(self):
        if self._directory:
            shutil.rmtree(self._directory, ignore_errors=True); self._directory = ""

    def __enter__(self): return self
    def __exit__(self, *_): self.close()
    def __del__(self): self.close()


class DocxVisualRenderer:
    def __init__(self, *, libreoffice_command: str = "libreoffice", pdftoppm_command: str = "pdftoppm", timeout_seconds: int = 60, max_pages: int = 25, max_dimension: int = 2400, max_image_bytes: int = 4 * 1024 * 1024, max_total_bytes: int = 20 * 1024 * 1024, runner: Callable = subprocess.run):
        self.libreoffice_command = libreoffice_command
        self.pdftoppm_command = pdftoppm_command
        self.timeout_seconds = timeout_seconds
        self.max_pages = max_pages; self.max_dimension = max_dimension
        self.max_image_bytes = max_image_bytes; self.max_total_bytes = max_total_bytes
        self.runner = runner

    def render(self, docx_bytes: bytes) -> RenderedDraft:
        directory = tempfile.mkdtemp(prefix="blueprint-docx-review-")
        try:
            root = Path(directory); input_path = root / "draft.docx"; output = root / "rendered"; profile = root / "lo-profile"
            output.mkdir(); profile.mkdir(); input_path.write_bytes(docx_bytes)
            command = [self.libreoffice_command, "--headless", f"-env:UserInstallation={profile.resolve().as_uri()}", "--convert-to", "pdf", "--outdir", str(output), str(input_path)]
            completed = self.runner(command, capture_output=True, timeout=self.timeout_seconds, check=False)
            if completed.returncode != 0:
                raise DocxVisualRenderError("libreoffice_failed", "LibreOffice conversion failed")
            pdf_path = output / "draft.pdf"
            if not pdf_path.is_file():
                candidates = list(output.glob("*.pdf")); pdf_path = candidates[0] if len(candidates) == 1 else pdf_path
            if not pdf_path.is_file(): raise DocxVisualRenderError("pdf_missing", "LibreOffice produced no PDF")
            pdf_bytes = pdf_path.read_bytes(); reader = PdfReader(io.BytesIO(pdf_bytes))
            if not 1 <= len(reader.pages) <= self.max_pages:
                raise DocxVisualRenderError("page_limit", "rendered page count exceeds limit")
            prefix = root / "page"
            ppm = self._resolve_pdftoppm()
            completed = self.runner([ppm, "-png", "-r", "144", str(pdf_path), str(prefix)], capture_output=True, timeout=self.timeout_seconds, check=False)
            if completed.returncode != 0: raise DocxVisualRenderError("page_render_failed", "PDF page rendering failed")
            image_paths = sorted(root.glob("page-*.png"))
            if len(image_paths) != len(reader.pages): raise DocxVisualRenderError("page_count_mismatch", "PDF and PNG page counts differ")
            pages = []; total = 0; findings = []
            for number, (page, image_path) in enumerate(zip(reader.pages, image_paths), 1):
                value = image_path.read_bytes(); total += len(value)
                with Image.open(io.BytesIO(value)) as image: width, height = image.size
                if width > self.max_dimension or height > self.max_dimension: raise DocxVisualRenderError("image_dimensions", "review image dimensions exceed limit")
                if len(value) > self.max_image_bytes or total > self.max_total_bytes: raise DocxVisualRenderError("image_bytes", "review image bytes exceed limit")
                text = (page.extract_text() or "").strip()
                if not text: findings.append(VisualFinding("blank_page", "error", number, "page has no extractable content"))
                elif len(text) < 40: findings.append(VisualFinding("sparse_page", "warning", number, "page contains unusually little text"))
                pages.append(PageImage(number, width, height, len(value), hashlib.sha256(value).hexdigest(), uuid.uuid4().hex, value))
            return RenderedDraft(directory, pdf_bytes, pages, findings, "libreoffice+poppler-v1")
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def _resolve_pdftoppm(self) -> str:
        command = shutil.which(self.pdftoppm_command) or self.pdftoppm_command
        if os.name == "nt" and command.lower().endswith(".cmd"):
            candidate = Path(command).resolve().parents[2] / "native" / "poppler" / "Library" / "bin" / "pdftoppm.exe"
            if candidate.is_file(): return str(candidate)
            candidate = Path(command).resolve().parent.parent / "Library" / "bin" / "pdftoppm.exe"
            if candidate.is_file(): return str(candidate)
        return command
