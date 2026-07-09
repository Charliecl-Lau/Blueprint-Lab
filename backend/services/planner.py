from backend.schemas.planner_schema import PlannerResponse
from backend.services.llm_client import LLMClient

_PLANNER_SYSTEM_PROMPT = """You are a structured assessment planner. Given an assessment prompt, produce a planning document that outlines the structure of every question before any question text is written.

For each question, specify:
- type: "mcq" or "long_answer"
- bloom_level: the Bloom's taxonomy action word (e.g., "Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create")
- topic: the specific sub-topic this question tests (unique — no two questions may share the same topic)
- answer_scope: a brief description of the expected answer length and depth

Return only valid JSON matching this schema exactly:
{
  "assessment_plan": {
    "questions": [
      {"type": "mcq", "bloom_level": "...", "topic": "...", "answer_scope": "..."}
    ]
  }
}"""


def generate_plan(llm: LLMClient, generated_prompt: str) -> PlannerResponse:
    user_message = f"Assessment prompt to plan:\n\n{generated_prompt}"
    raw = llm.generate_json(system_prompt=_PLANNER_SYSTEM_PROMPT, user_message=user_message)
    return PlannerResponse(**raw)
