from unittest.mock import MagicMock, patch
import pytest
from backend.models.run import Run, ControlSet
from backend.models.assessment import Assessment

@pytest.fixture
def run_with_assessment(test_db):
    run = Run(topic="TCP/IP", expectations="Test handshake", mcq_count=2, long_answer_count=1)
    test_db.add(run)
    test_db.commit()
    cs = ControlSet(run_id=run.id, personality="formal", prompt_length="medium", result_length="medium", action_word_count=2)
    test_db.add(cs)
    test_db.commit()
    a = Assessment(run_id=run.id, framework="forge", control_set_id=cs.id, status="pending")
    test_db.add(a)
    test_db.commit()
    return a, run, cs

MOCK_PROMPT_JSON = {"generated_prompt": "You are a test prompt..."}
MOCK_PLAN_JSON = {
    "assessment_plan": {
        "questions": [
            {"type": "mcq", "bloom_level": "Analyze", "topic": "SYN Flag", "answer_scope": "1 sentence"},
            {"type": "mcq", "bloom_level": "Apply", "topic": "ACK Flag", "answer_scope": "1 sentence"},
            {"type": "long_answer", "bloom_level": "Evaluate", "topic": "Congestion", "answer_scope": "2 paragraphs"},
        ]
    }
}
MOCK_GENERATION_JSON = {
    "questions": [
        {"type": "mcq", "body": "Q1?", "options": [{"body": "A", "is_correct": True}, {"body": "B", "is_correct": False}, {"body": "C", "is_correct": False}, {"body": "D", "is_correct": False}], "model_answer": None},
        {"type": "mcq", "body": "Q2?", "options": [{"body": "A", "is_correct": False}, {"body": "B", "is_correct": True}, {"body": "C", "is_correct": False}, {"body": "D", "is_correct": False}], "model_answer": None},
        {"type": "long_answer", "body": "Q3?", "options": [], "model_answer": "Model answer here."},
    ]
}

def test_pipeline_sets_status_complete(run_with_assessment, test_db):
    assessment, run, cs = run_with_assessment

    with patch("backend.workers.assessment_worker.LLMClient") as MockLLM, \
         patch("backend.workers.assessment_worker.SessionLocal") as MockSession, \
         patch("backend.workers.assessment_worker.redis_client") as mock_redis:

        MockSession.return_value = test_db
        test_db.close = MagicMock()  # prevent worker from closing the shared test session

        mock_llm_instance = MagicMock()
        mock_llm_instance.generate_json.side_effect = [
            MOCK_PROMPT_JSON,
            MOCK_PLAN_JSON,
            MOCK_GENERATION_JSON,
        ]
        MockLLM.return_value = mock_llm_instance

        from backend.workers.assessment_worker import run_assessment_pipeline
        run_assessment_pipeline(assessment.id)

        test_db.refresh(assessment)
        assert assessment.status == "complete"

def test_pipeline_sets_error_on_validation_failure(run_with_assessment, test_db):
    assessment, run, cs = run_with_assessment

    bad_plan = {
        "assessment_plan": {
            "questions": [
                {"type": "mcq", "bloom_level": "Analyze", "topic": "SYN Flag", "answer_scope": "1 sentence"},
                {"type": "long_answer", "bloom_level": "Evaluate", "topic": "Congestion", "answer_scope": "2 paragraphs"},
            ]
        }
    }

    with patch("backend.workers.assessment_worker.LLMClient") as MockLLM, \
         patch("backend.workers.assessment_worker.SessionLocal") as MockSession, \
         patch("backend.workers.assessment_worker.redis_client") as mock_redis:

        MockSession.return_value = test_db
        test_db.close = MagicMock()  # prevent worker from closing the shared test session

        mock_llm_instance = MagicMock()
        mock_llm_instance.generate_json.side_effect = [MOCK_PROMPT_JSON, bad_plan]
        MockLLM.return_value = mock_llm_instance

        from backend.workers.assessment_worker import run_assessment_pipeline
        run_assessment_pipeline(assessment.id)

        test_db.refresh(assessment)
        assert assessment.status == "error"
