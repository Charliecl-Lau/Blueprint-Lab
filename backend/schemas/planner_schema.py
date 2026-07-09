from typing import List, Literal
from pydantic import BaseModel

class QuestionPlan(BaseModel):
    type: Literal["mcq", "long_answer"]
    bloom_level: str
    topic: str
    answer_scope: str

class AssessmentPlan(BaseModel):
    questions: List[QuestionPlan]

class PlannerResponse(BaseModel):
    assessment_plan: AssessmentPlan
