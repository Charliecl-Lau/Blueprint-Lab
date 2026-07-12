from backend.services.reproducibility import (
    build_actual_prompt_hash,
    build_generation_envelope_hash,
    canonical_json,
    sha256_bytes,
    sha256_text,
)


def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'


def test_canonical_json_preserves_unicode():
    assert canonical_json({"topic": "café"}) == '{"topic":"café"}'


def test_text_and_bytes_hashes_use_utf8():
    assert sha256_text("café") == sha256_bytes("café".encode("utf-8"))


def test_actual_prompt_hash_changes_with_structure_input():
    common = dict(
        structure_system_prompt="structure",
        actual_prompt="actual",
        prompt_structure="openai",
        structure_prompt_version="2",
        actual_prompt_generator_version="2",
        model_settings={"temperature": 0.2},
    )
    assert build_actual_prompt_hash(**common, structure_input="A") != build_actual_prompt_hash(
        **common, structure_input="B"
    )


def test_generation_envelope_hash_changes_with_source_order():
    common = dict(
        actual_prompt="actual",
        generation_context="context",
        model_settings={"temperature": 0.2},
    )
    assert build_generation_envelope_hash(**common, source_hashes=["a", "b"]) != \
        build_generation_envelope_hash(**common, source_hashes=["b", "a"])
