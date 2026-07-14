from unittest.mock import MagicMock, patch

import pytest

from backend.models.experiment import Condition, Experiment, Generation
from backend.schemas.experiment_schema import PromptFactors
from backend.schemas.assessment_schema import (
    ASSESSMENT_PROVIDER_SCHEMA,
    AssessmentGenerationResponse,
)
from backend.services.llm_client import LLMResult
from backend.services.reproducibility import sha256_bytes, sha256_text
from backend.services.actual_prompt import (
    EQUATION_GENERATION_INSTRUCTION,
    build_generation_system_prompt,
    build_structure_input,
)
from backend.services.generation_context import build_generation_context
from backend.services.structure_system_prompts import get_structure_system_prompt


ACTUAL_PROMPT = """# Role
Assessment author
# Personality
Precise
# Goal
Generate questions
# Measure of Success
Correct questions
# Constraints
Use supplied facts
# Output
Return a JSON object with a top-level "questions" array
# Stop Rules
Stop after output"""


def complete_question(*, question_type, body, model_answer):
    return {
        "type": question_type,
        "metadata": {
            "question_title": "Equilibrium condition",
            "question_type": question_type,
            "difficulty_level": "introductory",
            "intended_assessment_setting": "In-class assessment",
            "mse202_concepts": ["Static equilibrium"],
            "mse302_concepts": ["Mechanical stability"],
            "concept_map_bridge": "Connects force balance to mechanical stability.",
            "materials_science_context": "Applies equilibrium to stable material systems.",
        },
        "body": body,
        "options": [],
        "model_answer": model_answer,
        "quality_check": [{
            "criterion": "Correctness",
            "rating": 5,
            "comment": "The equilibrium condition is technically correct.",
        }],
        "revision_options": [
            "Add a numerical force balance.",
            "Ask students to state assumptions.",
        ],
    }


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
                complete_question(
                    question_type="long_answer",
                    body="Explain equilibrium.",
                    model_answer="Net force and net moment are zero.",
                )
            ]
        })
        llm.generate.side_effect = [
            LLMResult(ACTUAL_PROMPT, "structure-123", "gemini", "structure-v", "STOP"),
            LLMResult(raw_text, "request-123", "gemini", "generation-v", "STOP"),
        ]
        MockLLM.return_value = llm

        from backend.workers.assessment_worker import run_generation_pipeline

        run_generation_pipeline(generation_fixture.id)

        test_db.refresh(generation_fixture)
        assert generation_fixture.status == "complete"
        assert generation_fixture.assessment.parsed_json["questions"][0]["body"] == "Explain equilibrium."
        assert generation_fixture.assessment.raw_response_text == raw_text
        assert generation_fixture.assessment.output_hash == sha256_text(raw_text)
        factors = generation_fixture.condition
        expected_input = build_structure_input(
            course=generation_fixture.experiment.course,
            topic=generation_fixture.experiment.topic,
            learning_objectives=generation_fixture.experiment.learning_objectives,
            assessment_type=generation_fixture.experiment.assessment_type,
            difficulty=generation_fixture.experiment.difficulty,
            number_of_questions=generation_fixture.experiment.number_of_questions,
            factors=PromptFactors(
                concept_bridge=factors.concept_bridge_enabled,
                few_shot=factors.few_shot_enabled,
                reference_content=factors.reference_content_enabled,
                reasoning_guidance=factors.reasoning_guidance_enabled,
            ),
            factor_inputs=factors.factor_inputs,
        )
        expected_system, _ = get_structure_system_prompt("openai")
        expected_context = build_generation_context([])
        assert [call.kwargs for call in llm.generate.call_args_list] == [
            {"system_prompt": expected_system, "user_message": expected_input,
             "model_settings": generation_fixture.model_settings},
            {"system_prompt": build_generation_system_prompt(ACTUAL_PROMPT), "user_message": expected_context,
             "model_settings": generation_fixture.model_settings,
             "response_schema": ASSESSMENT_PROVIDER_SCHEMA},
        ]
        assert generation_fixture.prompt.actual_prompt == ACTUAL_PROMPT
        assert EQUATION_GENERATION_INSTRUCTION in llm.generate.call_args_list[1].kwargs["system_prompt"]
        assert generation_fixture.prompt.actual_prompt_hash
        assert generation_fixture.prompt.generation_envelope_hash
        assert generation_fixture.prompt.structure_request_id == "structure-123"
        assert generation_fixture.prompt.structure_model_version == "structure-v"
        assert generation_fixture.prompt.structure_duration_ms is not None
        assert generation_fixture.document_artifact.content.startswith(b"PK")
        assert generation_fixture.document_artifact.content_hash == sha256_bytes(
            generation_fixture.document_artifact.content
        )
        assert generation_fixture.model_name == "gemini"
        assert generation_fixture.request_id == "request-123"
        assert generation_fixture.finish_reason == "STOP"
        assert generation_fixture.generation_time_ms is not None
        assert mock_redis.publish.called


def test_generation_retry_resumes_from_persisted_prompt(generation_fixture, test_db):
    valid_response = __import__("json").dumps({
        "questions": [complete_question(
            question_type="short_answer",
            body="State the equilibrium condition.",
            model_answer="Net force and moment are zero.",
        )]
    })
    with (
        patch("backend.workers.assessment_worker.LLMClient") as mock_client,
        patch("backend.workers.assessment_worker.SessionLocal", return_value=test_db),
        patch("backend.workers.assessment_worker.redis_client"),
    ):
        test_db.close = MagicMock()
        llm = mock_client.return_value
        llm.generate.side_effect = [
            LLMResult(ACTUAL_PROMPT, "structure", "gemini", "v", "STOP"),
            RuntimeError("temporary provider failure"),
        ]

        from backend.workers.assessment_worker import run_generation_pipeline

        with patch.object(
            run_generation_pipeline,
            "retry",
            side_effect=RuntimeError("retry scheduled"),
        ):
            with pytest.raises(RuntimeError, match="retry scheduled"):
                run_generation_pipeline(generation_fixture.id)

        test_db.refresh(generation_fixture)
        assert generation_fixture.prompt is not None

        llm.generate.reset_mock()
        llm.generate.side_effect = [
            LLMResult(valid_response, "generation", "gemini", "v", "STOP")
        ]
        run_generation_pipeline(generation_fixture.id)

        test_db.refresh(generation_fixture)
        assert generation_fixture.status == "complete"
        assert llm.generate.call_count == 1
        assert llm.generate.call_args.kwargs["response_schema"] is ASSESSMENT_PROVIDER_SCHEMA
        question_schema = ASSESSMENT_PROVIDER_SCHEMA["properties"]["questions"]["items"]
        assert set(question_schema["required"]) >= {
            "type", "body", "metadata", "quality_check", "revision_options"
        }
        assert "metadata" in question_schema["properties"]


def test_generation_pipeline_preserves_raw_response_when_parsing_fails(generation_fixture, test_db):
    with (
        patch("backend.workers.assessment_worker.LLMClient") as MockLLM,
        patch("backend.workers.assessment_worker.SessionLocal") as MockSession,
        patch("backend.workers.assessment_worker.redis_client"),
    ):
        MockSession.return_value = test_db
        test_db.close = MagicMock()
        MockLLM.return_value.generate.side_effect = [
            LLMResult(ACTUAL_PROMPT, "structure", "gemini", "v", "STOP"),
            LLMResult("not-json", "request-bad", "gemini", "v", "STOP"),
        ]

        from backend.workers.assessment_worker import run_generation_pipeline

        run_generation_pipeline(generation_fixture.id)

        test_db.refresh(generation_fixture)
        assert generation_fixture.status == "error"
        assert generation_fixture.assessment.raw_response_text == "not-json"
        assert generation_fixture.assessment.parsed_json is None
        assert generation_fixture.assessment.output_hash == sha256_text("not-json")
        assert generation_fixture.error_type == "assessment_parse_error"
        assert generation_fixture.prompt.prompt_hash


def test_malformed_actual_prompt_is_committed_before_validation(generation_fixture, test_db):
    with (
        patch("backend.workers.assessment_worker.LLMClient") as MockLLM,
        patch("backend.workers.assessment_worker.SessionLocal", return_value=test_db),
        patch("backend.workers.assessment_worker.redis_client"),
    ):
        test_db.close = MagicMock()
        MockLLM.return_value.generate.return_value = LLMResult(
            "not a structured prompt", "structure-bad", "gemini", "v", "STOP"
        )
        from backend.workers.assessment_worker import run_generation_pipeline
        run_generation_pipeline(generation_fixture.id)
        test_db.refresh(generation_fixture)
        assert generation_fixture.status == "error"
        assert generation_fixture.error_type == "actual_prompt_validation_error"
        assert generation_fixture.prompt.actual_prompt == "not a structured prompt"
        assert MockLLM.return_value.generate.call_count == 1


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        ([RuntimeError("structure failed")], "actual_prompt_provider_error"),
        ([LLMResult(ACTUAL_PROMPT, "s", "gemini", "v", "STOP"), RuntimeError("generation failed")],
         "generation_provider_error"),
    ],
)
def test_provider_failures_are_stage_specific(
    generation_fixture, test_db, side_effect, expected_error
):
    with (
        patch("backend.workers.assessment_worker.LLMClient") as MockLLM,
        patch("backend.workers.assessment_worker.SessionLocal", return_value=test_db),
        patch("backend.workers.assessment_worker.redis_client"),
    ):
        test_db.close = MagicMock()
        MockLLM.return_value.generate.side_effect = side_effect
        from backend.workers.assessment_worker import run_generation_pipeline
        with patch.object(run_generation_pipeline, "retry", side_effect=RuntimeError("retry scheduled")):
            with pytest.raises(RuntimeError, match="retry scheduled"):
                run_generation_pipeline(generation_fixture.id)
        test_db.refresh(generation_fixture)
        assert generation_fixture.status == "error"
        assert generation_fixture.error_type == expected_error


def test_generation_pipeline_ignores_missing_generation(test_db):
    with patch("backend.workers.assessment_worker.SessionLocal") as MockSession:
        MockSession.return_value = test_db
        test_db.close = MagicMock()

        from backend.workers.assessment_worker import run_generation_pipeline

        assert run_generation_pipeline(999_999) is None
