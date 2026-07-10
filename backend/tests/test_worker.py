from unittest.mock import MagicMock, patch

import pytest

from backend.models.experiment import Condition, Experiment, Generation


@pytest.fixture
def generation_fixture(test_db):
    experiment = Experiment(
        course="ENGR 101",
        topic="Statics",
        learning_objectives="Solve equilibrium problems.",
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=2,
    )
    test_db.add(experiment)
    test_db.flush()
    condition = Condition(
        experiment_id=experiment.id,
        prompt_structure="openai",
        course_bridge_enabled=True,
        few_shot_enabled=False,
        documents_enabled=True,
        condition_label="CourseBridge=ON; FewShot=OFF; Documents=ON",
    )
    test_db.add(condition)
    test_db.flush()
    generation = Generation(
        experiment_id=experiment.id,
        condition_id=condition.id,
        status="pending",
    )
    test_db.add(generation)
    test_db.commit()
    return generation


def test_generation_pipeline_logs_prompt_json_docx_and_metadata(generation_fixture, test_db):
    with (
        patch("backend.workers.assessment_worker.LLMClient") as MockLLM,
        patch("backend.workers.assessment_worker.SessionLocal") as MockSession,
        patch("backend.workers.assessment_worker.redis_client") as mock_redis,
    ):
        MockSession.return_value = test_db
        test_db.close = MagicMock()
        llm = MagicMock()
        llm.model_name = "gemini"
        llm.model_version = "gemini-2.0-flash"
        llm.generate_json.return_value = {
            "questions": [
                {
                    "type": "long_answer",
                    "body": "Explain equilibrium.",
                    "options": [],
                    "model_answer": "Net force and net moment are zero.",
                }
            ]
        }
        MockLLM.return_value = llm

        from backend.workers.assessment_worker import run_generation_pipeline

        run_generation_pipeline(generation_fixture.id)

        test_db.refresh(generation_fixture)
        assert generation_fixture.status == "complete"
        assert generation_fixture.generated_json["questions"][0]["body"] == "Explain equilibrium."
        assert generation_fixture.prompt_record.full_prompt
        assert generation_fixture.document_artifact.content.startswith(b"PK")
        assert generation_fixture.model_name == "gemini"
        assert generation_fixture.generation_time_ms is not None
        assert mock_redis.publish.called


def test_generation_pipeline_ignores_missing_generation(test_db):
    with patch("backend.workers.assessment_worker.SessionLocal") as MockSession:
        MockSession.return_value = test_db
        test_db.close = MagicMock()

        from backend.workers.assessment_worker import run_generation_pipeline

        assert run_generation_pipeline(999_999) is None
