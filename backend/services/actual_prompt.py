import re

from backend.schemas.experiment_schema import PromptFactors, PromptStructure


ACTUAL_PROMPT_GENERATOR_VERSION = "2"

_FACTOR_DEFINITIONS = (
    ("concept_bridge", "Concept Bridge"),
    ("few_shot", "Few-shot Examples"),
    ("reference_content", "Reference Content"),
    ("reasoning_guidance", "Reasoning Guidance"),
)
_OPENAI_SECTIONS = (
    "Role",
    "Personality",
    "Goal",
    "Measure of Success",
    "Constraints",
    "Output",
    "Stop Rules",
)
_ANTHROPIC_SECTIONS = (
    "context",
    "task",
    "constraints",
    "verification",
    "output_format",
    "reasoning_guidance",
)


class ActualPromptValidationError(ValueError):
    pass


def build_condition_label(factors: PromptFactors) -> str:
    return (
        f"ConceptBridge={'ON' if factors.concept_bridge else 'OFF'}; "
        f"FewShot={'ON' if factors.few_shot else 'OFF'}; "
        f"ReferenceContent={'ON' if factors.reference_content else 'OFF'}; "
        f"ReasoningGuidance={'ON' if factors.reasoning_guidance else 'OFF'}"
    )


def build_structure_input(
    *,
    course: str,
    topic: str,
    learning_objectives: str,
    assessment_type: str,
    difficulty: str,
    number_of_questions: int,
    factors: PromptFactors,
    factor_inputs: dict[str, str],
) -> str:
    sections = [
        "# Assessment Details",
        f"Course: {course}",
        f"Topic: {topic}",
        f"Learning Objectives: {learning_objectives}",
        f"Assessment Type: {assessment_type}",
        f"Difficulty: {difficulty}",
        f"Number of Questions: {number_of_questions}",
        "",
        "# Prompt Design Factors",
        f"Condition: {build_condition_label(factors)}",
    ]
    for name, label in _FACTOR_DEFINITIONS:
        if getattr(factors, name):
            sections.extend(("", f"## {label}", factor_inputs.get(name, "")))
    return "\n".join(sections)


def validate_actual_prompt(
    prompt_structure: PromptStructure, raw_text: str
) -> None:
    if not raw_text or raw_text.strip() != raw_text:
        raise ActualPromptValidationError(
            "Actual Prompt must be non-empty and have no leading or trailing whitespace"
        )
    if "```" in raw_text:
        raise ActualPromptValidationError("Actual Prompt must not use code fences")
    if '"questions"' not in raw_text:
        raise ActualPromptValidationError(
            'Actual Prompt must require a top-level "questions" array'
        )
    if prompt_structure == "anthropic":
        _validate_anthropic(raw_text)
    else:
        _validate_openai(raw_text)


def _validate_openai(raw_text: str) -> None:
    headings = re.findall(r"(?m)^# ([^\r\n]+)$", raw_text)
    if headings != list(_OPENAI_SECTIONS):
        raise ActualPromptValidationError(
            "OpenAI Actual Prompt must contain each required section exactly once and in order"
        )
    if not raw_text.startswith("# Role\n"):
        raise ActualPromptValidationError("OpenAI Actual Prompt must begin with # Role")


def _validate_anthropic(raw_text: str) -> None:
    for tag in _ANTHROPIC_SECTIONS:
        if raw_text.count(f"<{tag}>") != 1 or raw_text.count(f"</{tag}>") != 1:
            raise ActualPromptValidationError(
                f"Anthropic Actual Prompt must contain one balanced <{tag}> section"
            )
    pattern = r"\s*".join(
        rf"<{tag}>.+?</{tag}>" for tag in _ANTHROPIC_SECTIONS
    )
    if re.fullmatch(pattern, raw_text, flags=re.DOTALL) is None:
        raise ActualPromptValidationError(
            "Anthropic Actual Prompt sections must be balanced and in the required order"
        )
