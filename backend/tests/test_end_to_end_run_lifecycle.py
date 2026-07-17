import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.models import Experiment, Run
from backend.services.llm_client import LLMResult, TokenUsage


def valid_payload():
    return {
        "course": "ENGR 101",
        "topic": "Statics",
        "learning_objectives": "Solve equilibrium problems.",
        "assessment_type": "mixed",
        "difficulty": "introductory",
        "number_of_questions": 2,
        "estimated_time_minutes": 30,
        "prompt_structure": "openai",
        "factors": {
            "concept_bridge": False,
            "few_shot": False,
            "reference_content": False,
            "reasoning_guidance": False,
        },
        "factor_inputs": {},
    }


def create_valid_experiment(client, key):
    with patch("backend.api.experiments.run_generation_pipeline.delay"):
        response = client.post(
            "/experiments",
            headers={"Idempotency-Key": key},
            json=valid_payload(),
        )
    assert response.status_code == 200
    body = response.json()
    return SimpleNamespace(experiment_id=body["id"], run_id=body["runs"][0]["id"])


def assessment_response():
    return json.dumps({
        "questions": [{
            "type": "short_answer",
            "metadata": {
                "question_title": "Equilibrium condition",
                "question_type": "short_answer",
                "difficulty_level": "introductory",
                "intended_assessment_setting": "In-class assessment",
                "mse202_concepts": ["Static equilibrium"],
                "mse302_concepts": ["Mechanical stability"],
                "concept_map_bridge": "Connects force balance to stability.",
                "materials_science_context": "Applies equilibrium to stable systems.",
            },
            "body": "State the equilibrium condition.",
            "options": [],
            "model_answer": "Net force and moment are zero.",
            "quality_check": [{
                "criterion": "Correctness",
                "rating": 5,
                "comment": "The equilibrium condition is correct.",
            }],
            "revision_options": [
                "Add a numerical example.",
                "Ask students to state assumptions.",
            ],
        }],
    })


def llm_result(raw_text, response_id, usage):
    input_tokens, output_tokens, total_tokens = usage
    return LLMResult(
        raw_text=raw_text,
        provider_request_id=response_id,
        model_name="gemini",
        model_version="v1",
        finish_reason="STOP",
        usage=TokenUsage(
            input_tokens,
            output_tokens,
            total_tokens,
            None,
            None,
            {},
        ),
    )


def test_two_runs_finish_independently_and_reopen_with_isolated_tokens(client, test_db):
    first = create_valid_experiment(client, key="first")
    second = create_valid_experiment(client, key="second")

    def run_worker_with_mocked_gemini(run_id, usage):
        llm = MagicMock()
        llm.generate.return_value = llm_result(
            assessment_response(), f"{run_id}-assessment", usage
        )
        with (
            patch("backend.workers.assessment_worker.SessionLocal", return_value=test_db),
            patch("backend.workers.assessment_worker.LLMClient", return_value=llm),
            patch("backend.workers.assessment_worker.redis_client"),
            patch("backend.workers.assessment_worker.build_assessment_docx", return_value=b"docx"),
        ):
            test_db.close = MagicMock()
            from backend.workers.assessment_worker import run_generation_pipeline
            run_generation_pipeline.run(run_id)

    run_worker_with_mocked_gemini(first.run_id, usage=(20, 8, 28))
    run_worker_with_mocked_gemini(second.run_id, usage=(200, 80, 280))

    reopened = client.get(f"/runs/{first.run_id}").json()
    assert reopened["status"] == "complete", reopened
    assert reopened["token_usage"]["total_tokens"] == 28
    assert client.get(f"/runs/{second.run_id}").json()["token_usage"]["total_tokens"] == 280


def test_incomplete_submission_creates_no_research_rows_or_task(client, test_db):
    with patch("backend.api.experiments.run_generation_pipeline.delay") as delay:
        response = client.post(
            "/experiments",
            headers={"Idempotency-Key": "bad"},
            json={},
        )
    assert response.status_code == 422
    assert test_db.query(Experiment).count() == 0
    assert test_db.query(Run).count() == 0
    delay.assert_not_called()
