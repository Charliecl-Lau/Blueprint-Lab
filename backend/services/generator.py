import json

from backend.schemas.assessment_schema import AssessmentGenerationResponse
from backend.schemas.planner_schema import PlannerResponse
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


def generate_assessment(llm: LLMClient, plan: PlannerResponse) -> AssessmentGenerationResponse:
    """Compatibility adapter for the legacy worker until its migration task is executed."""
    return generate_questions(llm, json.dumps(plan.model_dump(), indent=2))
