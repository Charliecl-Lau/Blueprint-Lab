import hashlib
from types import SimpleNamespace

import pytest

from backend.services.generation_context import (
    SourceSnapshotError,
    build_generation_context,
)


def binding(*, binding_id, ordinal, text, content=None, name="Source", version="1"):
    included = text.encode("utf-8") if text is not None else content
    source = SimpleNamespace(
        name=name,
        version=version,
        extracted_text=text,
        content=content if content is not None else included,
    )
    return SimpleNamespace(
        id=binding_id,
        ordinal=ordinal,
        role="reference_content",
        included_text_hash=hashlib.sha256(included).hexdigest(),
        source_document=source,
    )


def test_empty_sources_use_neutral_generation_trigger():
    assert build_generation_context([]) == "Generate the assessment now."


def test_sources_are_ordered_and_preserve_exact_snapshot_text():
    later = binding(
        binding_id=1,
        ordinal=2,
        text="  exact later text\n",
        name='Reference "B"',
        version="2026&1",
    )
    first = binding(binding_id=2, ordinal=1, text="first", name="A")
    same_ordinal = binding(binding_id=3, ordinal=1, text="second", name="B")
    result = build_generation_context([later, same_ordinal, first])
    assert result.index('name="A"') < result.index('name="B"') < result.index('Reference &quot;B&quot;')
    assert 'version="2026&amp;1"' in result
    assert 'role="reference_content" ordinal="2"' in result
    assert "\n  exact later text\n\n</source>" in result


def test_binary_only_utf8_source_is_decoded_exactly():
    source = binding(binding_id=1, ordinal=0, text=None, content="snowman ☃".encode())
    assert "snowman ☃" in build_generation_context([source])


@pytest.mark.parametrize(
    "source",
    [
        binding(binding_id=1, ordinal=0, text=None, content=b"\xff"),
        binding(binding_id=1, ordinal=0, text="recorded"),
    ],
)
def test_unusable_or_mismatched_snapshots_fail(source):
    if source.source_document.extracted_text is not None:
        source.included_text_hash = "0" * 64
    with pytest.raises(SourceSnapshotError):
        build_generation_context([source])
