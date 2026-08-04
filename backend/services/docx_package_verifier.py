from __future__ import annotations

import hashlib
import io
import posixpath
import stat
import zipfile

from lxml import etree

from backend.services.docx_verification import VerificationIssue, VerificationReport


_NON_REPAIRABLE = {
    "archive_bomb",
    "embedded_executable",
    "external_relationship",
    "macro_content",
    "unsafe_archive_path",
    "symlink_part",
}
_FORBIDDEN_FRAGMENTS = (
    "vbaproject.bin",
    "activex/",
    "embeddings/",
    ".exe",
    ".dll",
    ".com",
    ".bat",
)
_REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}


class DocxPackageVerifier:
    def __init__(self, *, max_expanded_bytes: int = 100 * 1024 * 1024, max_ratio: int = 200):
        self.max_expanded_bytes = max_expanded_bytes
        self.max_ratio = max_ratio

    def verify(self, docx_bytes: bytes) -> VerificationReport:
        digest = hashlib.sha256(docx_bytes).hexdigest()
        issues: list[VerificationIssue] = []
        try:
            with zipfile.ZipFile(io.BytesIO(docx_bytes)) as archive:
                infos = archive.infolist()
                names = [item.filename for item in infos]
                if len(names) != len(set(names)):
                    issues.append(self._issue("duplicate_part", "duplicate ZIP member"))
                folded = [name.casefold() for name in names]
                if len(folded) != len(set(folded)):
                    issues.append(self._issue("duplicate_part", "case-colliding ZIP member"))
                expanded = sum(item.file_size for item in infos)
                if expanded > self.max_expanded_bytes:
                    issues.append(self._issue("archive_bomb", "expanded package size exceeds limit"))
                for item in infos:
                    normalized = posixpath.normpath(item.filename.replace("\\", "/"))
                    if normalized.startswith("../") or normalized.startswith("/") or normalized != item.filename.rstrip("/"):
                        issues.append(self._issue("unsafe_archive_path", "unsafe ZIP member path"))
                    mode = item.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        issues.append(self._issue("symlink_part", "ZIP member is a symlink"))
                    if item.compress_size and item.file_size / item.compress_size > self.max_ratio:
                        issues.append(self._issue("archive_bomb", "compression ratio exceeds limit"))
                    lowered = item.filename.casefold()
                    if not lowered.startswith(("word/", "_rels/", "docprops/", "customxml/")) and lowered != "[content_types].xml" and not lowered.endswith("/"):
                        issues.append(self._issue("unexpected_part", "unexpected package part"))
                    if any(fragment in lowered for fragment in _FORBIDDEN_FRAGMENTS):
                        code = "macro_content" if "vba" in lowered else "embedded_executable"
                        issues.append(self._issue(code, "forbidden embedded package part"))
                required = {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
                missing = required.difference(names)
                if missing:
                    issues.append(self._issue("missing_core_part", ",".join(sorted(missing))))
                if "[Content_Types].xml" in names:
                    self._check_content_types(archive.read("[Content_Types].xml"), issues)
                for name in names:
                    if name.endswith(".rels"):
                        self._check_relationships(archive.read(name), issues)
        except (zipfile.BadZipFile, OSError):
            issues.append(self._issue("invalid_docx_package", "not a valid OOXML ZIP package"))
        return VerificationReport(
            valid=not issues,
            issues=tuple(self._deduplicate(issues)),
            package_sha256=digest,
            tool_versions={"package_verifier": "1"},
        )

    def _issue(self, code: str, evidence: str) -> VerificationIssue:
        return VerificationIssue(
            code=code,
            repairable=code not in _NON_REPAIRABLE,
            evidence=evidence,
        )

    def _check_content_types(self, value: bytes, issues: list[VerificationIssue]) -> None:
        try:
            root = etree.fromstring(value)
        except etree.XMLSyntaxError:
            issues.append(self._issue("damaged_content_types", "content types XML is malformed"))
            return
        values = " ".join(root.xpath("//@ContentType")).casefold()
        if "macroenabled" in values or "vba" in values or "activex" in values:
            issues.append(self._issue("macro_content", "forbidden content type"))
        if "wordprocessingml.document.main+xml" not in values:
            issues.append(self._issue("damaged_content_types", "main document content type missing"))

    def _check_relationships(self, value: bytes, issues: list[VerificationIssue]) -> None:
        try:
            root = etree.fromstring(value)
        except etree.XMLSyntaxError:
            issues.append(self._issue("damaged_relationships", "relationship XML is malformed"))
            return
        for rel in root.xpath("//r:Relationship", namespaces=_REL_NS):
            target = (rel.get("Target") or "").casefold()
            rel_type = (rel.get("Type") or "").casefold()
            if (rel.get("TargetMode") or "").casefold() == "external":
                issues.append(self._issue("external_relationship", "external relationship is forbidden"))
            if "attachedtemplate" in rel_type or "oleobject" in rel_type or "activex" in rel_type:
                issues.append(self._issue("embedded_executable", "forbidden relationship type"))
            if target.startswith(("http:", "https:", "file:", "ftp:")):
                issues.append(self._issue("external_relationship", "remote relationship target"))

    @staticmethod
    def _deduplicate(issues):
        seen = set()
        for issue in issues:
            key = (issue.code, issue.evidence)
            if key not in seen:
                seen.add(key)
                yield issue
