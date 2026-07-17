from backend.schemas.experiment_schema import PromptFactors
from backend.services.actual_prompt import (
    ACTUAL_PROMPT_GENERATOR_VERSION,
    OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION,
    OPENAI_TEMPLATE_PROVENANCE,
    build_structure_input,
    render_openai_actual_prompt,
)
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
    assert build_actual_prompt_hash(
        **common, structure_input="A"
    ) != build_actual_prompt_hash(**common, structure_input="B")


def test_openai_template_and_hash_are_deterministic_for_identical_inputs():
    prompt_inputs = {
        "course": "MSE302",
        "topic": "Chemical Potential",
        "learning_objectives": "Analyze phase stability using chemical potential.",
        "assessment_type": "short_answer",
        "difficulty": "advanced",
        "number_of_questions": 2,
        "estimated_time_minutes": 40,
        "cognitive_demand": "apply_analyze",
        "additional_instruction": "Use one binary-alloy scenario.",
        "factors": PromptFactors(concept_bridge=True),
        "factor_inputs": {
            "concept_bridge": "Connect chemical potential to phase equilibrium."
        },
    }
    first_prompt = render_openai_actual_prompt(**prompt_inputs)
    second_prompt = render_openai_actual_prompt(**prompt_inputs)
    structure_input = build_structure_input(**prompt_inputs)
    hash_inputs = {
        "structure_system_prompt": OPENAI_TEMPLATE_PROVENANCE,
        "structure_input": structure_input,
        "prompt_structure": "openai",
        "structure_prompt_version": OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION,
        "actual_prompt_generator_version": ACTUAL_PROMPT_GENERATOR_VERSION,
        "model_settings": {"temperature": 0.2},
    }

    first_hash = build_actual_prompt_hash(
        **hash_inputs, actual_prompt=first_prompt
    )
    second_hash = build_actual_prompt_hash(
        **hash_inputs, actual_prompt=second_prompt
    )

    assert first_prompt == second_prompt
    assert first_hash == second_hash


def test_generation_envelope_hash_changes_with_source_order():
    common = dict(
        actual_prompt="actual",
        generation_context="context",
        model_settings={"temperature": 0.2},
    )
    assert build_generation_envelope_hash(**common, source_hashes=["a", "b"]) != \
        build_generation_envelope_hash(**common, source_hashes=["b", "a"])
