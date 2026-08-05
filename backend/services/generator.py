from typing import Optional

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


def generate_questions(
    raw_text: str,
    *,
    expected_questions: Optional[int] = None,
) -> AssessmentGenerationResponse:
    provider = ProviderAssessmentGenerationResponse.model_validate(
        _parse_json(raw_text)
    )
    if expected_questions is not None and len(provider.questions) != expected_questions:
        raise ValueError(
            f"expected {expected_questions} questions, received {len(provider.questions)}"
        )
    return AssessmentGenerationResponse.model_validate(
        _canonical_payload(provider)
    )
