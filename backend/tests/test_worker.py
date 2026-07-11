from unittest.mock import MagicMock, patch

import pytest

from backend.models.experiment import Condition, Experiment, Generation
from backend.services.llm_client import LLMResult
from backend.services.reproducibility import sha256_bytes, sha256_text


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
        concept_bridge_enabled=True,
        few_shot_enabled=False,
        reference_content_enabled=True,
        reasoning_guidance_enabled=False,
        factor_inputs={"concept_bridge": "Vectors", "reference_content": "SI units"},
        condition_label="ConceptBridge=ON; FewShot=OFF; ReferenceContent=ON; ReasoningGuidance=OFF",
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
        raw_text = __import__("json").dumps({
            "questions": [
                {
                    "type": "long_answer",
                    "body": "Explain equilibrium.",
                    "options": [],
                    "model_answer": "Net force and net moment are zero.",
                }
            ]
        })
        llm.generate.return_value = LLMResult(
            raw_text=raw_text, provider_request_id="request-123",
            model_name="gemini", model_version="gemini-2.0-flash",
            finish_reason="STOP",
        )
        MockLLM.return_value = llm

        from backend.workers.assessment_worker import run_generation_pipeline

        run_generation_pipeline(generation_fixture.id)

        test_db.refresh(generation_fixture)
        assert generation_fixture.status == "complete"
        assert generation_fixture.assessment.parsed_json["questions"][0]["body"] == "Explain equilibrium."
        assert generation_fixture.assessment.raw_response_text == raw_text
        assert generation_fixture.assessment.output_hash == sha256_text(raw_text)
        assert generation_fixture.prompt.prompt_hash
        assert generation_fixture.document_artifact.content.startswith(b"PK")
        assert generation_fixture.document_artifact.content_hash == sha256_bytes(
            generation_fixture.document_artifact.content
        )
        assert generation_fixture.model_name == "gemini"
        assert generation_fixture.request_id == "request-123"
        assert generation_fixture.finish_reason == "STOP"
        assert generation_fixture.generation_time_ms is not None
        assert mock_redis.publish.called


def test_generation_pipeline_preserves_raw_response_when_parsing_fails(generation_fixture, test_db):
    with (
        patch("backend.workers.assessment_worker.LLMClient") as MockLLM,
        patch("backend.workers.assessment_worker.SessionLocal") as MockSession,
        patch("backend.workers.assessment_worker.redis_client"),
    ):
        MockSession.return_value = test_db
        test_db.close = MagicMock()
        MockLLM.return_value.generate.return_value = LLMResult(
            raw_text="not-json", provider_request_id="request-bad",
            model_name="gemini", model_version="gemini-2.0-flash",
            finish_reason="STOP",
        )

        from backend.workers.assessment_worker import run_generation_pipeline

        run_generation_pipeline(generation_fixture.id)

        test_db.refresh(generation_fixture)
        assert generation_fixture.status == "error"
        assert generation_fixture.assessment.raw_response_text == "not-json"
        assert generation_fixture.assessment.parsed_json is None
        assert generation_fixture.assessment.output_hash == sha256_text("not-json")
        assert generation_fixture.error_type == "assessment_parse_error"
        assert generation_fixture.prompt.prompt_hash


def test_generation_pipeline_ignores_missing_generation(test_db):
    with patch("backend.workers.assessment_worker.SessionLocal") as MockSession:
        MockSession.return_value = test_db
        test_db.close = MagicMock()

        from backend.workers.assessment_worker import run_generation_pipeline

        assert run_generation_pipeline(999_999) is None
