from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class MCQOptionSchema(BaseModel):
    body: str
    is_correct: bool

class QuestionResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    type: Literal["mcq", "long_answer"]
    body: str
    options: List[MCQOptionSchema] = Field(default_factory=list)
    model_answer: Optional[str]

class AssessmentGenerationResponse(BaseModel):
    questions: List[QuestionResponse]
