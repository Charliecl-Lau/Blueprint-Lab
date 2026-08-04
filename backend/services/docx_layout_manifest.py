"""Compiler-owned layout evidence; never authored independently by the model."""

from __future__ import annotations

import hashlib
import json


MANIFEST_VERSION = "agentic-docx-layout-v1"


def canonical_manifest_bytes(manifest: dict) -> bytes:
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def manifest_sha256(manifest: dict) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()
