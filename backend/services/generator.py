import json
from backend.schemas.planner_schema import PlannerResponse
from backend.schemas.assessment_schema import AssessmentGenerationResponse
from backend.services.llm_client import LLMClient

_GENERATOR_SYSTEM_PROMPT = """You are an expert educational assessment writer. Given a structured assessment plan, write all questions in full.

For MCQ questions:
- Write a clear, unambiguous question body
- Provide exactly 4 options: exactly one must be correct (is_correct: true), three must be plausible distractors
- Set model_answer to null

For long answer questions:
- Write a clear, open-ended question body
- Set options to an empty array []
- Write a complete model answer appropriate to the answer_scope in the plan

Return only valid JSON matching this schema:
{
  "questions": [
    {
      "type": "mcq",
      "body": "...",
      "options": [{"body": "...", "is_correct": false}, ...],
      "model_answer": null
    },
    {
      "type": "long_answer",
      "body": "...",
      "options": [],
      "model_answer": "..."
    }
  ]
}

Generate questions in the same order as the plan. Do not skip any question."""


def generate_assessment(llm: LLMClient, plan: PlannerResponse) -> AssessmentGenerationResponse:
    plan_text = json.dumps(plan.model_dump(), indent=2)
    user_message = f"Assessment plan to execute:\n\n{plan_text}"
    raw = llm.generate_json(system_prompt=_GENERATOR_SYSTEM_PROMPT, user_message=user_message)
    return AssessmentGenerationResponse(**raw)
