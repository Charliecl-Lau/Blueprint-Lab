import hashlib
import json
from typing import List


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def build_prompt_hash(
    system_prompt: str,
    final_prompt: str,
    prompt_structure: str,
    prompt_template_version: str,
    prompt_generator_version: str,
    model_settings: dict,
    source_hashes: List[str],
) -> str:
    envelope = {
        "system_prompt": system_prompt,
        "final_prompt": final_prompt,
        "prompt_structure": prompt_structure,
        "prompt_template_version": prompt_template_version,
        "prompt_generator_version": prompt_generator_version,
        "model_settings": model_settings,
        "source_hashes": source_hashes,
    }
    return sha256_text(canonical_json(envelope))
