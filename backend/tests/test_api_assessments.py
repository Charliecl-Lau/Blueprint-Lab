from backend.models.run import Run, ControlSet
from backend.models.assessment import Assessment
from backend.models.question import Question, MCQOption, ModelAnswer

def _seed_assessment(test_db):
    run = Run(topic="TCP/IP", expectations="test", mcq_count=1, long_answer_count=1)
    test_db.add(run)
    test_db.commit()
    cs = ControlSet(run_id=run.id, personality="formal", prompt_length="medium", result_length="medium", action_word_count=2)
    test_db.add(cs)
    test_db.commit()
    a = Assessment(run_id=run.id, framework="forge", control_set_id=cs.id, status="complete")
    test_db.add(a)
    test_db.commit()

    q1 = Question(assessment_id=a.id, type="mcq", body="What is SYN?", order=0)
    test_db.add(q1)
    test_db.flush()
    test_db.add(MCQOption(question_id=q1.id, body="Synchronize", is_correct=True))
    test_db.add(MCQOption(question_id=q1.id, body="Signal", is_correct=False))
    test_db.add(MCQOption(question_id=q1.id, body="Send", is_correct=False))
    test_db.add(MCQOption(question_id=q1.id, body="System", is_correct=False))

    q2 = Question(assessment_id=a.id, type="long_answer", body="Explain congestion control.", order=1)
    test_db.add(q2)
    test_db.flush()
    test_db.add(ModelAnswer(question_id=q2.id, body="TCP uses slow start..."))
    test_db.commit()
    return a

def test_get_assessment(client, test_db):
    a = _seed_assessment(test_db)
    response = client.get(f"/assessments/{a.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == a.id
    assert data["framework"] == "forge"
    assert len(data["questions"]) == 2
    assert data["questions"][0]["type"] == "mcq"
    assert len(data["questions"][0]["options"]) == 4

def test_get_assessment_not_found(client):
    response = client.get("/assessments/999")
    assert response.status_code == 404

def test_regenerate_assessment(client, test_db):
    from unittest.mock import patch
    a = _seed_assessment(test_db)
    with patch("backend.api.assessments.run_assessment_pipeline") as mock_task:
        mock_task.delay = lambda x: None
        response = client.post(f"/assessments/{a.id}/regenerate")
    assert response.status_code == 200
    data = response.json()
    assert data["assessment_id"] == a.id
    assert data["status"] == "pending"

def test_export_pdf_student(client, test_db):
    from unittest.mock import patch, MagicMock
    a = _seed_assessment(test_db)
    fake_pdf = b"%PDF-fake"
    mock_html_cls = MagicMock()
    mock_html_cls.return_value.write_pdf.return_value = fake_pdf
    with patch("backend.api.assessments.HTML", mock_html_cls):
        response = client.post(f"/assessments/{a.id}/export-pdf?variant=student")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == fake_pdf

def test_export_pdf_answer_key(client, test_db):
    from unittest.mock import patch, MagicMock
    a = _seed_assessment(test_db)
    fake_pdf = b"%PDF-fake"
    mock_html_cls = MagicMock()
    mock_html_cls.return_value.write_pdf.return_value = fake_pdf
    with patch("backend.api.assessments.HTML", mock_html_cls):
        response = client.post(f"/assessments/{a.id}/export-pdf?variant=answer_key")
    assert response.status_code == 200
    assert response.content == fake_pdf

def test_export_pdf_invalid_variant(client, test_db):
    a = _seed_assessment(test_db)
    response = client.post(f"/assessments/{a.id}/export-pdf?variant=invalid")
    assert response.status_code == 422
