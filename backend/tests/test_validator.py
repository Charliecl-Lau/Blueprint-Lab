import pytest
from backend.schemas.planner_schema import PlannerResponse
from backend.services.validator import validate_plan, ValidationResult


def _make_plan(questions):
    return PlannerResponse(assessment_plan={"questions": questions})

def _mcq(topic, bloom="Analyze"):
    return {"type": "mcq", "bloom_level": bloom, "topic": topic, "answer_scope": "2 sentences"}

def _la(topic, bloom="Evaluate"):
    return {"type": "long_answer", "bloom_level": bloom, "topic": topic, "answer_scope": "3 paragraphs"}


def test_valid_plan_passes():
    questions = (
        [_mcq(f"Topic {i}", bloom="Analyze") for i in range(6)]
        + [_mcq(f"Topic {i+6}", bloom="Apply") for i in range(4)]
        + [_la(f"LA Topic {i}", bloom="Evaluate") for i in range(3)]
    )
    plan = _make_plan(questions)
    result = validate_plan(plan, mcq_count=10, long_answer_count=3)
    assert result.passed is True
    assert result.errors == []

def test_wrong_mcq_count_fails():
    questions = [_mcq(f"Topic {i}") for i in range(8)] + [_la(f"LA Topic {i}") for i in range(3)]
    plan = _make_plan(questions)
    result = validate_plan(plan, mcq_count=10, long_answer_count=3)
    assert result.passed is False
    assert any("MCQ" in e for e in result.errors)

def test_wrong_long_answer_count_fails():
    questions = [_mcq(f"Topic {i}") for i in range(10)] + [_la(f"LA Topic {i}") for i in range(2)]
    plan = _make_plan(questions)
    result = validate_plan(plan, mcq_count=10, long_answer_count=3)
    assert result.passed is False
    assert any("long answer" in e.lower() for e in result.errors)

def test_repeated_topic_fails():
    questions = [_mcq("TCP Handshake") for _ in range(10)] + [_la(f"LA Topic {i}") for i in range(3)]
    plan = _make_plan(questions)
    result = validate_plan(plan, mcq_count=10, long_answer_count=3)
    assert result.passed is False
    assert any("repeated" in e.lower() for e in result.errors)

def test_bloom_concentration_fails():
    # All 10 MCQs use "Analyze" — that's 77% of 13 questions, exceeds 60%
    questions = [_mcq(f"Topic {i}", bloom="Analyze") for i in range(10)] + [_la(f"LA Topic {i}") for i in range(3)]
    plan = _make_plan(questions)
    result = validate_plan(plan, mcq_count=10, long_answer_count=3)
    assert result.passed is False
    assert any("bloom" in e.lower() or "60%" in e for e in result.errors)

def test_empty_answer_scope_fails():
    questions = (
        [_mcq(f"Topic {i}") for i in range(9)]
        + [{"type": "mcq", "bloom_level": "Apply", "topic": "Topic 9", "answer_scope": ""}]
        + [_la(f"LA Topic {i}") for i in range(3)]
    )
    plan = _make_plan(questions)
    result = validate_plan(plan, mcq_count=10, long_answer_count=3)
    assert result.passed is False
    assert any("answer_scope" in e.lower() or "empty" in e.lower() for e in result.errors)
