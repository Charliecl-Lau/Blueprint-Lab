import hashlib
import json


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def build_actual_prompt_hash(
    *,
    structure_system_prompt: str,
    structure_input: str,
    actual_prompt: str,
    prompt_structure: str,
    structure_prompt_version: str,
    actual_prompt_generator_version: str,
    model_settings: dict,
) -> str:
    return sha256_text(canonical_json({
        "structure_system_prompt": structure_system_prompt,
        "structure_input": structure_input,
        "actual_prompt": actual_prompt,
        "prompt_structure": prompt_structure,
        "structure_prompt_version": structure_prompt_version,
        "actual_prompt_generator_version": actual_prompt_generator_version,
        "model_settings": model_settings,
    }))


def build_generation_envelope_hash(
    *,
    actual_prompt: str,
    generation_context: str,
    model_settings: dict,
    source_hashes: list[str],
) -> str:
    return sha256_text(canonical_json({
        "actual_prompt": actual_prompt,
        "generation_context": generation_context,
        "model_settings": model_settings,
        "source_hashes": source_hashes,
    }))


def build_prompt_hash(
    system_prompt: str,
    final_prompt: str,
    prompt_structure: str,
    prompt_template_version: str,
    prompt_generator_version: str,
    model_settings: dict,
    source_hashes: list[str],
) -> str:
    """Build the legacy single-stage envelope hash during worker migration."""
    return sha256_text(canonical_json({
        "system_prompt": system_prompt,
        "final_prompt": final_prompt,
        "prompt_structure": prompt_structure,
        "prompt_template_version": prompt_template_version,
        "prompt_generator_version": prompt_generator_version,
        "model_settings": model_settings,
        "source_hashes": source_hashes,
    }))
