from backend.schemas.assessment_schema import AssessmentGenerationResponse
from backend.services.llm_client import LLMClient


_QUESTION_GENERATOR_SYSTEM_PROMPT = """Execute the provided generated research prompt directly.

Generate the assessment without an intermediate planning stage. Do not add, remove, or reinterpret
provider-specific prompt sections. Follow the JSON schema embedded in the generated prompt and return
only valid JSON.
"""


def generate_questions(llm: LLMClient, generated_prompt: str) -> AssessmentGenerationResponse:
    raw = llm.generate_json(
        system_prompt=_QUESTION_GENERATOR_SYSTEM_PROMPT,
        user_message=generated_prompt,
    )
    return AssessmentGenerationResponse(**raw)
