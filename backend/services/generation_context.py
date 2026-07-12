import hashlib
from html import escape
from typing import Sequence

from backend.models.source_document import RunSourceDocument


class SourceSnapshotError(ValueError):
    pass


def build_generation_context(bindings: Sequence[RunSourceDocument]) -> str:
    if not bindings:
        return "Generate the assessment now."

    blocks = []
    for binding in sorted(bindings, key=lambda item: (item.ordinal, item.id)):
        source = binding.source_document
        if source.extracted_text is not None:
            text = source.extracted_text
            included_bytes = text.encode("utf-8")
        else:
            included_bytes = source.content
            try:
                text = included_bytes.decode("utf-8")
            except (AttributeError, UnicodeDecodeError) as exc:
                raise SourceSnapshotError(
                    f"Source binding {binding.id} has no usable text snapshot"
                ) from exc

        digest = hashlib.sha256(included_bytes).hexdigest()
        if digest != binding.included_text_hash:
            raise SourceSnapshotError(
                f"Source binding {binding.id} does not match its recorded text hash"
            )

        attributes = (
            f'role="{escape(binding.role, quote=True)}" '
            f'ordinal="{binding.ordinal}" '
            f'name="{escape(source.name, quote=True)}" '
            f'version="{escape(source.version, quote=True)}"'
        )
        blocks.append(f"<source {attributes}>\n{text}\n</source>")
    return "\n\n".join(blocks)

