from unittest.mock import MagicMock
import pytest
from backend.schemas.planner_schema import PlannerResponse
from backend.schemas.assessment_schema import AssessmentGenerationResponse
from backend.services.generator import generate_assessment

VALID_PLAN = PlannerResponse(assessment_plan={"questions": [
    {"type": "mcq", "bloom_level": "Analyze", "topic": "TCP Handshake", "answer_scope": "2 sentences"},
    {"type": "long_answer", "bloom_level": "Evaluate", "topic": "Congestion control", "answer_scope": "3 paragraphs"},
]})

VALID_GENERATION_JSON = {
    "questions": [
        {
            "type": "mcq",
            "body": "What is the purpose of the SYN flag?",
            "options": [
                {"body": "Initiate a connection", "is_correct": True},
                {"body": "Terminate a connection", "is_correct": False},
                {"body": "Acknowledge data", "is_correct": False},
                {"body": "Request retransmission", "is_correct": False},
            ],
            "model_answer": None,
        },
        {
            "type": "long_answer",
            "body": "Explain TCP congestion control mechanisms.",
            "options": [],
            "model_answer": "TCP uses slow start, congestion avoidance, fast retransmit...",
        },
    ]
}

@pytest.fixture
def mock_llm():
    client = MagicMock()
    client.generate_json.return_value = VALID_GENERATION_JSON
    return client

def test_generate_assessment_returns_response(mock_llm):
    result = generate_assessment(llm=mock_llm, plan=VALID_PLAN)
    assert isinstance(result, AssessmentGenerationResponse)
    assert len(result.questions) == 2

def test_mcq_has_four_options(mock_llm):
    result = generate_assessment(llm=mock_llm, plan=VALID_PLAN)
    mcq = result.questions[0]
    assert mcq.type == "mcq"
    assert len(mcq.options) == 4
    assert sum(1 for o in mcq.options if o.is_correct) == 1

def test_long_answer_has_model_answer(mock_llm):
    result = generate_assessment(llm=mock_llm, plan=VALID_PLAN)
    la = result.questions[1]
    assert la.type == "long_answer"
    assert la.model_answer is not None
