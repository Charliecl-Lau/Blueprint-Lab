from pathlib import Path

import pytest

from backend.schemas.experiment_schema import PromptFactors
from backend.services.actual_prompt import (
    ActualPromptValidationError,
    build_generation_system_prompt,
    build_condition_label,
    build_structure_input,
    validate_actual_prompt,
)
from backend.services.structure_system_prompts import get_structure_system_prompt


def test_provider_structures_are_distinct_and_versioned():
    openai_prompt, openai_version = get_structure_system_prompt("openai")
    anthropic_prompt, anthropic_version = get_structure_system_prompt("anthropic")
    assert openai_prompt
    assert anthropic_prompt
    assert openai_prompt != anthropic_prompt
    assert openai_version == anthropic_version == "10"


def test_provider_structures_require_questions_array_contract():
    for structure in ("openai", "anthropic"):
        system_prompt, _ = get_structure_system_prompt(structure)
        assert '"questions"' in system_prompt
        assert "type" in system_prompt
        assert "body" in system_prompt
        assert "Assessment Quality Requirements" not in system_prompt
        assert "quality_check" not in system_prompt


def test_reference_prompt_does_not_require_assessment_quality_check():
    reference_prompt = Path("prompt/chatgpt-system-prompt.md").read_text(encoding="utf-8")

    assert "Assessment Quality Check" not in reference_prompt


def test_generation_and_structure_prompts_require_flat_word_equation_entries():
    generation_prompt = build_generation_system_prompt(OPENAI_ACTUAL_PROMPT)
    for required_text in (
        "native Microsoft Word OMML",
        "equations[]",
        "expression",
        "Microsoft Word linear equation syntax",
        "equations = []",
        "sqrt(...)",
        "[[EQ:label]]",
    ):
        assert required_text in generation_prompt
    assert "structured math AST" not in generation_prompt
    assert "body_segments" not in generation_prompt

    for structure in ("openai", "anthropic"):
        system_prompt, _ = get_structure_system_prompt(structure)
        assert "native Microsoft Word OMML" in system_prompt
        assert "equations[]" in system_prompt
        assert "Microsoft Word linear equation syntax" in system_prompt
        assert "[[EQ:label]]" in system_prompt
        assert "structured math AST" not in system_prompt
        assert "body_segments" not in system_prompt


def test_structure_input_contains_details_and_enabled_factor_values_only():
    text = build_structure_input(
        course="MSE202",
        topic="Gibbs Phase Rule",
        learning_objectives="Apply the phase rule.",
        assessment_type="short_answer",
        difficulty="medium",
        number_of_questions=1,
        cognitive_demand="evaluate_create",
        additional_instruction="Use one laboratory scenario.",
        factors=PromptFactors(concept_bridge=True),
        factor_inputs={
            "concept_bridge": "Criterion for equilibrium",
            "few_shot": "must not appear",
        },
    )
    assert "Assessment Details" in text
    assert "Prompt Design Factors" in text
    assert "ConceptBridge=ON" in text
    assert "FewShot=OFF" in text
    assert "Criterion for equilibrium" in text
    assert "Cognitive Demand: Evaluate/Create" in text
    assert "Additional Instruction: Use one laboratory scenario." in text
    assert "must not appear" not in text


def test_structure_input_omits_blank_additional_instruction():
    text = build_structure_input(
        course="MSE202",
        topic="Gibbs Phase Rule",
        learning_objectives="Apply the phase rule.",
        assessment_type="short_answer",
        difficulty="medium",
        number_of_questions=1,
        cognitive_demand="remember_understand",
        additional_instruction="   ",
        factors=PromptFactors(),
        factor_inputs={},
    )

    assert "Cognitive Demand: Remember/Understand" in text
    assert "Additional Instruction" not in text


def test_condition_label_records_all_factor_states():
    assert build_condition_label(PromptFactors(concept_bridge=True)) == (
        "ConceptBridge=ON; FewShot=OFF; ReferenceContent=OFF; "
        "ReasoningGuidance=OFF"
    )


OPENAI_ACTUAL_PROMPT = """# Role
Assessment author
# Personality
Precise
# Goal
Generate questions
# Measure of Success
Correct questions
# Constraints
Use supplied facts
# Output
Return a JSON object with a top-level "questions" array
# Stop Rules
Stop after output"""

ANTHROPIC_ACTUAL_PROMPT = """<context>Course context</context>
<task>Generate questions</task>
<constraints>Use supplied facts</constraints>
<verification>Check correctness</verification>
<output_format>Return a JSON object with a top-level "questions" array</output_format>
<reasoning_guidance>Use concise rationale</reasoning_guidance>"""


@pytest.mark.parametrize(
    ("structure", "raw_text"),
    [
        ("openai", ""),
        ("openai", f"```markdown\n{OPENAI_ACTUAL_PROMPT}\n```"),
        ("openai", f"Here is the prompt:\n{OPENAI_ACTUAL_PROMPT}"),
        (
            "openai",
            OPENAI_ACTUAL_PROMPT.replace(
                '# Output\nReturn a JSON object with a top-level "questions" array\n',
                "",
            ),
        ),
        ("anthropic", ANTHROPIC_ACTUAL_PROMPT.replace("<verification>", "<context>")),
        ("anthropic", ANTHROPIC_ACTUAL_PROMPT + "\n<context>duplicate</context>"),
        ("anthropic", ANTHROPIC_ACTUAL_PROMPT.replace("</task>", "")),
    ],
)
def test_invalid_actual_prompts_are_rejected(structure, raw_text):
    with pytest.raises(ActualPromptValidationError):
        validate_actual_prompt(structure, raw_text)


@pytest.mark.parametrize(
    ("structure", "raw_text"),
    [
        ("openai", OPENAI_ACTUAL_PROMPT.replace('top-level "questions" array', "JSON object")),
        ("anthropic", ANTHROPIC_ACTUAL_PROMPT.replace('top-level "questions" array', "JSON object")),
    ],
)
def test_actual_prompts_without_questions_array_contract_are_rejected(structure, raw_text):
    with pytest.raises(ActualPromptValidationError, match="questions"):
        validate_actual_prompt(structure, raw_text)


@pytest.mark.parametrize(
    ("structure", "raw_text"),
    [("openai", OPENAI_ACTUAL_PROMPT), ("anthropic", ANTHROPIC_ACTUAL_PROMPT)],
)
def test_valid_actual_prompts_are_accepted_without_rewriting(structure, raw_text):
    assert validate_actual_prompt(structure, raw_text) is None
