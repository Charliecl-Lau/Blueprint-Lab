from backend.schemas.assessment_schema import AssessmentGenerationResponse
from backend.services.llm_client import _parse_json


_QUESTION_GENERATOR_SYSTEM_PROMPT = """Execute the provided generated research prompt directly.

Generate the assessment without an intermediate planning stage. Do not add, remove, or reinterpret
provider-specific prompt sections. Follow the JSON schema embedded in the generated prompt and return
only valid JSON.
"""


def generate_questions(raw_text: str) -> AssessmentGenerationResponse:
    return AssessmentGenerationResponse(**_parse_json(raw_text))
