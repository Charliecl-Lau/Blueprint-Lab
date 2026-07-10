from typing import Optional

from backend.schemas.experiment_schema import PromptFactors, PromptStructure
from backend.services.research_system_prompt import BLUEPRINT_LAB_SYSTEM_PROMPT


def build_condition_label(factors: PromptFactors) -> str:
    return (
        f"ConceptBridge={'ON' if factors.concept_bridge else 'OFF'}; "
        f"FewShot={'ON' if factors.few_shot else 'OFF'}; "
        f"ReferenceContent={'ON' if factors.reference_content else 'OFF'}; "
        f"ReasoningGuidance={'ON' if factors.reasoning_guidance else 'OFF'}"
    )


def _factor_sections(factors: PromptFactors, inputs: dict[str, str]) -> str:
    definitions = (
        ("concept_bridge", "Concept Bridge"),
        ("few_shot", "Few-shot Examples"),
        ("reference_content", "Reference Content"),
        ("reasoning_guidance", "Reasoning Guidance"),
    )
    return "\n\n".join(
        f"## {label}\n{inputs[name]}" for name, label in definitions if getattr(factors, name)
    )


def build_research_prompt(*, prompt_structure: PromptStructure, course: str, topic: str,
                          learning_objectives: str, assessment_type: str, difficulty: str,
                          number_of_questions: int, factors: PromptFactors,
                          factor_inputs: Optional[dict[str, str]] = None) -> str:
    shared = (
        f"Prompt Structure: {prompt_structure}\nExperiment Condition: {build_condition_label(factors)}\n"
        f"Course: {course}\nTopic: {topic}\nLearning Objectives: {learning_objectives}\n"
        f"Assessment Type: {assessment_type}\nDifficulty: {difficulty}\nNumber of Questions: {number_of_questions}"
    )
    factor_sections = _factor_sections(factors, factor_inputs or {}) or "No optional prompt design factors are enabled."
    if prompt_structure == "anthropic":
        return (
            f"<context>\n{BLUEPRINT_LAB_SYSTEM_PROMPT}\n{shared}\n{factor_sections}\n</context>\n\n"
            "<task>\nGenerate the requested assessment questions directly. Do not create a separate plan.\n</task>\n\n"
            "<constraints>\nKeep the prompt structure fixed.\n</constraints>\n\n"
            "<verification>\nVerify correctness, unit consistency, course alignment, and schema completeness.\n</verification>\n\n"
            "<output_format>\nReturn only valid JSON matching the system prompt schema.\n</output_format>\n\n"
            "<reasoning_guidance>\nProvide only requested concise rationale or structured solution steps; do not expose hidden private reasoning.\n</reasoning_guidance>"
        )
    return (
        f"# Role\n{BLUEPRINT_LAB_SYSTEM_PROMPT}\n\n# Goal\n{shared}\n\n# Prompt Design Factors\n{factor_sections}\n\n"
        "# Measure of Success\nProduce correct, traceable, DOCX-ready assessment content.\n\n"
        "# Constraints\nKeep the structure fixed.\n\n# Output\nReturn only valid JSON matching the system prompt schema.\n\n"
        "# Stop Rules\nIf a required research input is missing, return a schema-valid error object."
    )
