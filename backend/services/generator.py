from backend.schemas.assessment_schema import (
    AssessmentGenerationResponse,
    ProviderAssessmentGenerationResponse,
)
from backend.services.llm_client import _parse_json
from backend.services.omml import parse_linear_expression


def _canonical_payload(
    provider: ProviderAssessmentGenerationResponse,
) -> dict:
    payload = provider.model_dump()
    for question in payload["questions"]:
        for equation in question["equations"]:
            equation["math"] = parse_linear_expression(
                equation["expression"]
            )
    return payload


def generate_questions(raw_text: str) -> AssessmentGenerationResponse:
    provider = ProviderAssessmentGenerationResponse.model_validate(
        _parse_json(raw_text)
    )
    return AssessmentGenerationResponse.model_validate(
        _canonical_payload(provider)
    )
