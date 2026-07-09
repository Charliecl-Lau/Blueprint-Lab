from backend.models.run import Run, ControlSet
from backend.models.assessment import Assessment, PromptGeneration, PlannerOutput, AssessmentGeneration
from backend.models.question import Question, MCQOption, ModelAnswer

def test_create_run(test_db):
    run = Run(topic="TCP/IP", expectations="Test understanding of handshake", mcq_count=10, long_answer_count=3)
    test_db.add(run)
    test_db.commit()
    assert run.id is not None

def test_create_control_set(test_db):
    run = Run(topic="TCP/IP", expectations="Test handshake", mcq_count=10, long_answer_count=3)
    test_db.add(run)
    test_db.commit()
    cs = ControlSet(run_id=run.id, personality="formal", prompt_length="medium", result_length="medium", action_word_count=3)
    test_db.add(cs)
    test_db.commit()
    assert cs.id is not None
    assert cs.run_id == run.id

def test_create_assessment(test_db):
    run = Run(topic="TCP/IP", expectations="Test handshake", mcq_count=10, long_answer_count=3)
    test_db.add(run)
    test_db.commit()
    cs = ControlSet(run_id=run.id, personality="formal", prompt_length="medium", result_length="medium", action_word_count=3)
    test_db.add(cs)
    test_db.commit()
    a = Assessment(run_id=run.id, framework="forge", control_set_id=cs.id, status="pending")
    test_db.add(a)
    test_db.commit()
    assert a.id is not None
    assert a.status == "pending"
