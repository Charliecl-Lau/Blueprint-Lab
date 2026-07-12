from backend.schemas.experiment_schema import PromptStructure


STRUCTURE_PROMPT_VERSION = "2"

OPENAI_STRUCTURE_SYSTEM_PROMPT = """You generate the Actual Prompt that will control a later assessment-generation call.
Return only the completed Actual Prompt, with no code fence, preface, commentary, or trailing text.
Use exactly these Markdown sections in this order: # Role, # Personality, # Goal,
# Measure of Success, # Constraints, # Output, and # Stop Rules. Incorporate the
assessment details and only factor inputs marked ON. Do not invent content for factors
marked OFF. Make the prompt instruct the later model to return the requested assessment
as valid JSON."""

ANTHROPIC_STRUCTURE_SYSTEM_PROMPT = """You generate the Actual Prompt that will control a later assessment-generation call.
Return only the completed Actual Prompt, with no code fence, preface, commentary, or trailing text.
Use exactly these XML sections in this order: <context>, <task>, <constraints>,
<verification>, <output_format>, and <reasoning_guidance>. Include one balanced pair
of each tag. Incorporate the assessment details and only factor inputs marked ON. Do
not invent content for factors marked OFF. Make the prompt instruct the later model to
return the requested assessment as valid JSON."""


def get_structure_system_prompt(
    prompt_structure: PromptStructure,
) -> tuple[str, str]:
    if prompt_structure == "anthropic":
        return ANTHROPIC_STRUCTURE_SYSTEM_PROMPT, STRUCTURE_PROMPT_VERSION
    return OPENAI_STRUCTURE_SYSTEM_PROMPT, STRUCTURE_PROMPT_VERSION
