from backend.schemas.experiment_schema import PromptFactors, PromptStructure
from backend.services.research_system_prompt import BLUEPRINT_LAB_SYSTEM_PROMPT


def build_condition_label(factors: PromptFactors) -> str:
    return (
        f"CourseBridge={'ON' if factors.course_bridge else 'OFF'}; "
        f"FewShot={'ON' if factors.few_shot else 'OFF'}; "
        f"Documents={'ON' if factors.documents else 'OFF'}"
    )


def _factor_sections(factors: PromptFactors) -> str:
    sections = []
    if factors.course_bridge:
        sections.append("## Course Bridge\nExplicitly connect the MSE202 prerequisite concept to the MSE302 thermodynamics concept.")
    if factors.few_shot:
        sections.append("## Few-shot Examples\nUse supplied examples only as guides for style and rigor; generate new content.")
    if factors.documents:
        sections.append("## Instructor Examples / Attached Documents\nTreat supplied documents as constraints on terminology, notation, scope, and solution style.")
    return "\n\n".join(sections)


def build_research_prompt(*, prompt_structure: PromptStructure, course: str, topic: str,
                          learning_objectives: str, assessment_type: str, difficulty: str,
                          number_of_questions: int, factors: PromptFactors) -> str:
    shared = (
        f"Prompt Structure: {prompt_structure}\nExperiment Condition: {build_condition_label(factors)}\n"
        f"Course: {course}\nTopic: {topic}\nLearning Objectives: {learning_objectives}\n"
        f"Assessment Type: {assessment_type}\nDifficulty: {difficulty}\n"
        f"Number of Questions: {number_of_questions}"
    )
    factor_sections = _factor_sections(factors) or "No optional prompt design factors are enabled."

    if prompt_structure == "anthropic":
        return (
            f"<context>\n{BLUEPRINT_LAB_SYSTEM_PROMPT}\n{shared}\n{factor_sections}\n</context>\n\n"
            "<task>\nGenerate the requested assessment questions directly. Do not create a separate plan.\n</task>\n\n"
            "<constraints>\nKeep the prompt structure fixed. Preserve supplied traceability IDs exactly.\n</constraints>\n\n"
            "<verification>\nVerify correctness, unit consistency, course alignment, schema completeness, and MCQ answer uniqueness.\n</verification>\n\n"
            "<output_format>\nReturn only valid JSON matching the system prompt schema.\n</output_format>\n\n"
            "<reasoning_guidance>\nEstablish the concept bridge, construct and solve the problem, verify it, then serialize the final result.\n</reasoning_guidance>"
        )

    return (
        f"# Role\n{BLUEPRINT_LAB_SYSTEM_PROMPT}\n\n# Goal\n{shared}\n\n"
        f"# Prompt Design Factors\n{factor_sections}\n\n"
        "# Measure of Success\nProduce correct, traceable, DOCX-ready assessment content.\n\n"
        "# Constraints\nKeep the structure fixed and preserve supplied IDs.\n\n"
        "# Output\nReturn only valid JSON matching the system prompt schema.\n\n"
        "# Stop Rules\nIf a required research input is missing, return a schema-valid error object."
    )
