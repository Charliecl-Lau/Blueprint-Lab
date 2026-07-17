from unittest.mock import patch

from backend.config import settings
from backend.services.evaluation_service import create_human_draft
from backend.services.assessment_rubric import CRITERION_KEYS
from backend.tests.test_evaluation_service import evaluated_run


def test_questions_evaluations_and_grading_context_routes(client, test_db):
    run = evaluated_run(test_db, question_count=3)
    first, middle, last = sorted(run.assessment.questions, key=lambda item: item.ordinal)
    create_human_draft(test_db, middle.id, "another-reviewer")

    questions = client.get(
        f"/assessments/{run.assessment.id}/questions"
    )
    context = client.get(
        f"/assessment-questions/{middle.id}/grading-context"
    )
    evaluations = client.get(
        f"/assessments/{run.assessment.id}/evaluations"
    )

    assert questions.status_code == 200
    assert [item["id"] for item in questions.json()] == [
        first.id,
        middle.id,
        last.id,
    ]
    assert questions.json()[1]["question"]["metadata"]["question_title"] == "Question 2"
    assert context.status_code == 200
    body = context.json()
    assert body["previous_question_id"] == first.id
    assert body["next_question_id"] == last.id
    assert body["human_evaluation"]["evaluator_identity"] == settings.local_reviewer_id
    assert body["llm_evaluation"]["evaluation_type"] == "llm"
    assert body["llm_evaluation"]["criteria"][0]["justification"].startswith("LLM evidence")
    assert body["viewer_path"] == f"/experiments/{run.experiment_id}/viewer/{run.id}"
    assert evaluations.status_code == 200
    assert len(evaluations.json()) == 5


def test_grading_context_returns_409_before_llm_completion(client, test_db):
    run = evaluated_run(test_db, question_count=1)
    llm_evaluation = next(
        item
        for item in run.assessment.questions[0].evaluations
        if item.evaluation_type == "llm"
    )
    llm_evaluation.status = "failed"
    test_db.commit()

    response = client.get(
        f"/assessment-questions/{run.assessment.questions[0].id}/grading-context"
    )

    assert response.status_code == 409
    assert "unavailable" in response.json()["detail"].lower()


def test_human_draft_patch_finalize_reopen_and_comparison_routes(client, test_db):
    run = evaluated_run(test_db, question_count=1)
    question = run.assessment.questions[0]
    created = client.post(
        f"/assessment-questions/{question.id}/evaluations/human",
        json={},
    )
    assert created.status_code == 200
    draft = created.json()

    incomplete = client.post(f"/evaluations/{draft['id']}/finalize")
    assert incomplete.status_code == 422

    criteria = [
        {"criterion_key": key, "score": 4, "comment": f"Comment for {key}"}
        for key in CRITERION_KEYS
    ]
    patched = client.patch(
        f"/evaluations/{draft['id']}",
        json={
            "revision": draft["revision"],
            "criteria": criteria,
            "overall_comments": "Ready with minor revisions.",
        },
    )
    assert patched.status_code == 200
    assert patched.json()["revision"] == 2
    assert patched.json()["weighted_score"] == 80.0

    stale = client.patch(
        f"/evaluations/{draft['id']}",
        json={"revision": 1, "overall_comments": "stale edit"},
    )
    assert stale.status_code == 409

    finalized = client.post(f"/evaluations/{draft['id']}/finalize")
    assert finalized.status_code == 200
    assert finalized.json()["status"] == "finalized"
    comparison = client.get(
        f"/assessment-questions/{question.id}/evaluation-comparison"
    )
    assert comparison.status_code == 200
    comparison_body = comparison.json()
    assert comparison_body["human_weighted_score"] == 80.0
    assert "winner" not in comparison_body
    assert "correct_evaluator" not in comparison_body

    locked = client.patch(
        f"/evaluations/{draft['id']}",
        json={"revision": 2, "overall_comments": "must reopen"},
    )
    assert locked.status_code == 409
    reopened = client.post(f"/evaluations/{draft['id']}/reopen")
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "reopened"
    assert reopened.json()["revision"] == 3


def test_llm_access_route_records_first_open_once_and_llm_is_read_only(client, test_db):
    run = evaluated_run(test_db, question_count=1)
    question = run.assessment.questions[0]
    human = client.post(
        f"/assessment-questions/{question.id}/evaluations/human", json={}
    ).json()
    llm = next(
        item for item in question.evaluations if item.evaluation_type == "llm"
    )

    first = client.post(
        f"/evaluations/{human['id']}/llm-access",
        json={"llm_evaluation_id": llm.id},
    )
    second = client.post(
        f"/evaluations/{human['id']}/llm-access",
        json={"llm_evaluation_id": llm.id},
    )

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["opened_before_finalization"] is True
    read_only = client.patch(
        f"/evaluations/{llm.id}",
        json={"revision": 1, "overall_comments": "change LLM"},
    )
    assert read_only.status_code == 409


def test_comparison_is_unavailable_before_human_finalization(client, test_db):
    run = evaluated_run(test_db, question_count=1)
    question = run.assessment.questions[0]
    client.post(f"/assessment-questions/{question.id}/evaluations/human", json={})

    response = client.get(
        f"/assessment-questions/{question.id}/evaluation-comparison"
    )

    assert response.status_code == 409


def test_llm_retry_route_dispatches_only_evaluation_worker(client, test_db):
    run = evaluated_run(test_db, question_count=1)
    run.viewer_ready_at = run.created_at
    llm_evaluation = next(
        item
        for item in run.assessment.questions[0].evaluations
        if item.evaluation_type == "llm"
    )
    llm_evaluation.status = "failed"
    test_db.commit()

    with (
        patch(
            "backend.workers.evaluation_worker.run_llm_evaluation_pipeline.delay"
        ) as evaluation_delay,
        patch(
            "backend.workers.assessment_worker.run_generation_pipeline.delay"
        ) as generation_delay,
    ):
        response = client.post(
            f"/assessments/{run.assessment.id}/evaluations/llm/retry"
        )

    assert response.status_code == 200
    assert response.json()["status"] == "complete"
    evaluation_delay.assert_called_once_with(run.id)
    generation_delay.assert_not_called()
