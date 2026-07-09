from unittest.mock import MagicMock
import pytest
from backend.schemas.planner_schema import PlannerResponse
from backend.services.planner import generate_plan

VALID_PLAN_JSON = {
    "assessment_plan": {
        "questions": [
            {"type": "mcq", "bloom_level": "Analyze", "topic": "TCP Handshake", "answer_scope": "2-3 sentences"},
            {"type": "long_answer", "bloom_level": "Evaluate", "topic": "Congestion control", "answer_scope": "3 paragraphs"},
        ]
    }
}

@pytest.fixture
def mock_llm():
    client = MagicMock()
    client.generate_json.return_value = VALID_PLAN_JSON
    return client

def test_generate_plan_returns_planner_response(mock_llm):
    result = generate_plan(
        llm=mock_llm,
        generated_prompt="You are an assessment generator about TCP/IP...",
    )
    assert isinstance(result, PlannerResponse)
    assert len(result.assessment_plan.questions) == 2

def test_generate_plan_calls_llm_with_generated_prompt(mock_llm):
    generate_plan(llm=mock_llm, generated_prompt="Test prompt text")
    user_message = mock_llm.generate_json.call_args.kwargs["user_message"]
    assert "Test prompt text" in user_message

def test_generate_plan_raises_on_invalid_llm_response(mock_llm):
    mock_llm.generate_json.return_value = {"wrong_structure": {}}
    with pytest.raises(Exception):
        generate_plan(llm=mock_llm, generated_prompt="test")
