from backend.schemas.assessment_schema import AssessmentGenerationResponse
from backend.services.llm_client import _parse_json


def generate_questions(raw_text: str) -> AssessmentGenerationResponse:
    return AssessmentGenerationResponse(**_parse_json(raw_text))
