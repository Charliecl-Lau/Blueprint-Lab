from backend.services.reproducibility import build_prompt_hash, canonical_json, sha256_bytes, sha256_text


def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'


def test_canonical_json_preserves_unicode():
    assert canonical_json({"topic": "café"}) == '{"topic":"café"}'


def test_text_and_bytes_hashes_use_utf8():
    assert sha256_text("café") == sha256_bytes("café".encode("utf-8"))


def test_prompt_hash_changes_when_source_order_changes():
    common = dict(
        system_prompt="S",
        final_prompt="U",
        prompt_structure="openai",
        prompt_template_version="1",
        prompt_generator_version="1",
        model_settings={"temperature": 0.2},
    )
    assert build_prompt_hash(**common, source_hashes=["a", "b"]) != build_prompt_hash(
        **common, source_hashes=["b", "a"]
    )
