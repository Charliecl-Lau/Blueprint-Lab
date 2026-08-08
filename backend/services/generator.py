from typing import Optional

from backend.schemas.assessment_schema import (
    AssessmentGenerationResponse,
    ProviderAssessmentGenerationResponse,
    ProviderQuestionResponse,
)
from backend.services.assessment_segment_compiler import (
    compile_provider_assessment,
    compile_provider_question,
)
from backend.services.llm_client import _parse_json
from backend.services.omml import parse_linear_expression


def generate_questions(
    raw_text: str,
    *,
    expected_questions: Optional[int] = None,
) -> AssessmentGenerationResponse:
    payload = _parse_json(raw_text)
    try:
        provider = ProviderAssessmentGenerationResponse.model_validate(payload)
    except Exception:
        # Historical assessments and in-flight retries may still use the former
        # flat provider contract. Keep that path readable while all newly sent
        # provider schemas are segment-first.
        return AssessmentGenerationResponse.model_validate(
            _legacy_canonical_payload(payload, expected_questions)
        )
    return compile_provider_assessment(
        provider, expected_questions=expected_questions
    )


def parse_segmented_assessment(raw_text: str) -> ProviderAssessmentGenerationResponse:
    return ProviderAssessmentGenerationResponse.model_validate(_parse_json(raw_text))


def parse_segmented_question(raw_text: str) -> ProviderQuestionResponse:
    return ProviderQuestionResponse.model_validate(_parse_json(raw_text))


def generate_segmented_question(raw_text: str, question_ordinal: int):
    return compile_provider_question(
        parse_segmented_question(raw_text), question_ordinal
    )


def _legacy_canonical_payload(payload: dict, expected_questions: Optional[int]) -> dict:
    questions = payload.get("questions", []) if isinstance(payload, dict) else []
    if expected_questions is not None and len(questions) != expected_questions:
        raise ValueError(
            f"expected {expected_questions} questions, received {len(questions)}"
        )
    canonical = dict(payload)
    canonical_questions = []
    for source in questions:
        question = dict(source)
        equations = []
        for source_equation in question.get("equations", []):
            equation = dict(source_equation)
            equation["math"] = parse_linear_expression(equation["expression"])
            equations.append(equation)
        question["equations"] = equations
        canonical_questions.append(question)
    canonical["questions"] = canonical_questions
    return canonical
