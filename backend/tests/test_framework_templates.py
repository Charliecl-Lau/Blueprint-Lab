import pytest

from backend.services.framework_templates import build_framework_system_prompt

def test_forge_template_contains_required_sections():
    prompt = build_framework_system_prompt(
        framework="forge",
        personality="formal",
        prompt_length="medium",
        result_length="medium",
        action_word_count=3,
    )
    for section in ["<context>", "<task>", "<constraints>", "<verification>", "<output_format>", "<reasoning_guidance>"]:
        assert section in prompt, f"Missing section: {section}"

def test_openai_template_contains_required_sections():
    prompt = build_framework_system_prompt(
        framework="openai",
        personality="socratic",
        prompt_length="short",
        result_length="long",
        action_word_count=2,
    )
    for section in ["# Role", "# Personality", "# Goal", "# Measure of Success", "# Constraints", "# Output", "# Stop Rules"]:
        assert section in prompt, f"Missing section: {section}"

def test_risen_template_contains_required_sections():
    prompt = build_framework_system_prompt(
        framework="risen",
        personality="encouraging",
        prompt_length="long",
        result_length="short",
        action_word_count=4,
    )
    for section in ["<role>", "<instructions>", "<step>", "<end_goal>", "<narrowing>"]:
        assert section in prompt, f"Missing section: {section}"

def test_personality_appears_in_prompt():
    prompt = build_framework_system_prompt(
        framework="forge", personality="socratic", prompt_length="medium",
        result_length="medium", action_word_count=3,
    )
    assert "socratic" in prompt.lower()

def test_invalid_framework_raises():
    with pytest.raises(ValueError, match="Unknown framework"):
        build_framework_system_prompt(
            framework="unknown", personality="formal", prompt_length="medium",
            result_length="medium", action_word_count=3,
        )
