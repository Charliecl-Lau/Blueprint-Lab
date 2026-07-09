import pytest
from pydantic import ValidationError
from backend.schemas.prompt_schema import PromptGenerationResponse
from backend.schemas.planner_schema import PlannerResponse, QuestionPlan
from backend.schemas.assessment_schema import AssessmentGenerationResponse, MCQOptionSchema, QuestionResponse

def test_prompt_schema_valid():
    r = PromptGenerationResponse(generated_prompt="Generate questions about TCP/IP...")
    assert r.generated_prompt == "Generate questions about TCP/IP..."

def test_prompt_schema_missing_field():
    with pytest.raises(ValidationError):
        PromptGenerationResponse()

def test_planner_schema_valid():
    plan_data = {
        "assessment_plan": {
            "questions": [
                {"type": "mcq", "bloom_level": "Analyze", "topic": "TCP Handshake", "answer_scope": "2-3 sentences"},
                {"type": "long_answer", "bloom_level": "Evaluate", "topic": "Congestion control", "answer_scope": "3-4 paragraphs"},
            ]
        }
    }
    r = PlannerResponse(**plan_data)
    assert len(r.assessment_plan.questions) == 2
    assert r.assessment_plan.questions[0].type == "mcq"

def test_planner_schema_invalid_type():
    with pytest.raises(ValidationError):
        PlannerResponse(assessment_plan={"questions": [{"type": "essay", "bloom_level": "X", "topic": "Y", "answer_scope": "Z"}]})

def test_assessment_schema_valid():
    data = {
        "questions": [
            {
                "type": "mcq",
                "body": "What does SYN stand for?",
                "options": [
                    {"body": "Synchronize", "is_correct": True},
                    {"body": "System", "is_correct": False},
                    {"body": "Signal", "is_correct": False},
                    {"body": "Send", "is_correct": False},
                ],
                "model_answer": None,
            }
        ]
    }
    r = AssessmentGenerationResponse(**data)
    assert r.questions[0].type == "mcq"
    assert r.questions[0].options[0].is_correct is True
