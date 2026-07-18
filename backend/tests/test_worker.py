from unittest.mock import MagicMock, call, patch

import pytest
from celery.exceptions import MaxRetriesExceededError, Retry

from backend.models import ModelCallUsage, RunReferencePdf
from backend.models.experiment import Condition, Experiment, Generation
from backend.schemas.experiment_schema import PromptFactors
from backend.schemas.assessment_schema import (
    ASSESSMENT_PROVIDER_SCHEMA,
    AssessmentGenerationResponse,
)
from backend.services.llm_client import LLMResult, TokenUsage, TruncatedResponseError
from backend.services.reference_pdfs import ProviderFileAttachment
from backend.services.reproducibility import sha256_text
from backend.services.actual_prompt import (
    ActualPromptValidationError,
    EQUATION_GENERATION_INSTRUCTION,
    OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION,
    OPENAI_TEMPLATE_PROVENANCE,
    build_assessment_repair_system_prompt,
    build_generation_system_prompt,
    build_structure_input,
    render_openai_actual_prompt,
)
from backend.services.generation_context import build_generation_context
from backend.services.structure_system_prompts import get_structure_system_prompt


ANTHROPIC_ACTUAL_PROMPT = """<context>Course context</context>
<task>Generate questions</task>
<constraints>Use supplied facts</constraints>
<verification>Check correctness</verification>
<output_format>Return a JSON object with a top-level "questions" array</output_format>
<reasoning_guidance>Use concise rationale</reasoning_guidance>"""


def result(raw_text, input_tokens, output_tokens, total_tokens, finish="STOP"):
    return LLMResult(
        raw_text=raw_text,
        provider_request_id=f"response-{total_tokens}",
        model_name="gemini",
        model_version="v1",
        finish_reason=finish,
        usage=TokenUsage(
            input_tokens,
            output_tokens,
            total_tokens,
            None,
            None,
            {},
        ),
    )


def run_pipeline_synchronously(run, test_db, llm, attachments=None):
    with (
        patch("backend.workers.assessment_worker.LLMClient", return_value=llm),
        patch("backend.workers.assessment_worker.SessionLocal", return_value=test_db),
        patch("backend.workers.assessment_worker.redis_client") as mock_redis,
        patch(
            "backend.services.document_artifact.build_assessment_docx",
            return_value=b"PK-generation-docx",
        ),
        patch(
            "backend.workers.assessment_worker.run_llm_evaluation_pipeline.delay"
        ) as evaluation_delay,
    ):
        test_db.close = MagicMock()
        from backend.workers.assessment_worker import run_generation_pipeline

        run_generation_pipeline.run(
            run.id,
            [attachment.to_dict() for attachment in (attachments or [])],
        )
        mock_redis.evaluation_delay = evaluation_delay
        return mock_redis


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
        cognitive_demand="evaluate_create",
        additional_instruction="Use one laboratory scenario.",
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
        factor_inputs={"concept_bridge": "Vectors"},
        condition_label="ConceptBridge=ON; FewShot=OFF; ReferenceContent=ON; ReasoningGuidance=OFF",
    )
    test_db.add(condition)
    test_db.flush()
    generation = Generation(
        experiment_id=experiment.id,
        condition_id=condition.id,
        status="pending",
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        model_call_count=0,
    )
    generation.reference_pdfs = [
        RunReferencePdf(ordinal=0, original_filename="one.pdf"),
        RunReferencePdf(ordinal=1, original_filename="two.pdf"),
    ]
    test_db.add(generation)
    test_db.commit()
    return generation


def test_generation_pipeline_logs_prompt_json_docx_and_metadata(generation_fixture, test_db):
    with (
        patch("backend.workers.assessment_worker.LLMClient") as MockLLM,
        patch("backend.workers.assessment_worker.SessionLocal") as MockSession,
        patch("backend.workers.assessment_worker.redis_client") as mock_redis,
        patch(
            "backend.services.document_artifact.build_assessment_docx",
            return_value=b"PK-generation-docx",
        ),
        patch(
            "backend.workers.assessment_worker.run_llm_evaluation_pipeline.delay"
        ) as evaluation_delay,
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
        llm.generate.return_value = LLMResult(
            raw_text, "request-123", "gemini", "generation-v", "STOP"
        )
        MockLLM.return_value = llm

        from backend.workers.assessment_worker import run_generation_pipeline

        run_generation_pipeline(generation_fixture.id)

        test_db.refresh(generation_fixture)
        assert generation_fixture.status == "complete"
        assert generation_fixture.completed_at is not None
        assert generation_fixture.viewer_ready_at is not None
        assert generation_fixture.progress_message == "Complete"
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
            estimated_time_minutes=(
                generation_fixture.experiment.estimated_time_minutes
            ),
            cognitive_demand=generation_fixture.experiment.cognitive_demand,
            additional_instruction=generation_fixture.experiment.additional_instruction,
            factors=PromptFactors(
                concept_bridge=factors.concept_bridge_enabled,
                few_shot=factors.few_shot_enabled,
                reference_content=factors.reference_content_enabled,
                reasoning_guidance=factors.reasoning_guidance_enabled,
            ),
            factor_inputs=factors.factor_inputs,
            reference_pdf_filenames=generation_fixture.reference_pdf_filenames,
        )
        expected_prompt = render_openai_actual_prompt(
            course=generation_fixture.experiment.course,
            topic=generation_fixture.experiment.topic,
            learning_objectives=generation_fixture.experiment.learning_objectives,
            assessment_type=generation_fixture.experiment.assessment_type,
            difficulty=generation_fixture.experiment.difficulty,
            number_of_questions=generation_fixture.experiment.number_of_questions,
            estimated_time_minutes=(
                generation_fixture.experiment.estimated_time_minutes
            ),
            cognitive_demand=generation_fixture.experiment.cognitive_demand,
            additional_instruction=(
                generation_fixture.experiment.additional_instruction
            ),
            factors=PromptFactors(
                concept_bridge=factors.concept_bridge_enabled,
                few_shot=factors.few_shot_enabled,
                reference_content=factors.reference_content_enabled,
                reasoning_guidance=factors.reasoning_guidance_enabled,
            ),
            factor_inputs=factors.factor_inputs,
            reference_pdf_filenames=generation_fixture.reference_pdf_filenames,
        )
        expected_context = build_generation_context([])
        assert [call.kwargs for call in llm.generate.call_args_list] == [
            {"system_prompt": build_generation_system_prompt(expected_prompt), "user_message": expected_context,
             "model_settings": generation_fixture.model_settings,
             "response_schema": ASSESSMENT_PROVIDER_SCHEMA},
        ]
        assert generation_fixture.prompt.structure_input == expected_input
        assert generation_fixture.prompt.actual_prompt == expected_prompt
        assert generation_fixture.prompt.structure_system_prompt == OPENAI_TEMPLATE_PROVENANCE
        assert generation_fixture.prompt.structure_prompt_version == OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION
        assert generation_fixture.prompt.structure_request_id is None
        assert generation_fixture.prompt.structure_model == "local-template-renderer"
        assert generation_fixture.prompt.structure_model_version == OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION
        assert generation_fixture.prompt.structure_finish_reason == "LOCAL"
        assert EQUATION_GENERATION_INSTRUCTION in llm.generate.call_args_list[0].kwargs["system_prompt"]
        assert generation_fixture.prompt.actual_prompt_hash
        assert generation_fixture.prompt.generation_envelope_hash
        assert generation_fixture.prompt.structure_duration_ms is not None
        assert generation_fixture.document_artifact.content == b"PK-generation-docx"
        assert len(generation_fixture.assessment.questions) == 1
        evaluation_delay.assert_called_once_with(generation_fixture.id)
        assert generation_fixture.model_name == "gemini"
        assert generation_fixture.request_id == "request-123"
        assert generation_fixture.finish_reason == "STOP"
        assert generation_fixture.generation_time_ms is not None
        assert mock_redis.publish.called


def test_anthropic_pipeline_retains_provider_prompt_compilation(
    generation_fixture, test_db
):
    generation_fixture.condition.prompt_structure = "anthropic"
    test_db.commit()
    raw_text = __import__("json").dumps(
        {
            "questions": [
                complete_question(
                    question_type="short_answer",
                    body="State equilibrium.",
                    model_answer="Forces and moments balance.",
                )
            ]
        }
    )
    llm = MagicMock()
    llm.generate.side_effect = [
        result(ANTHROPIC_ACTUAL_PROMPT, 10, 5, 15),
        result(raw_text, 20, 8, 28),
    ]

    run_pipeline_synchronously(generation_fixture, test_db, llm)

    expected_system, expected_version = get_structure_system_prompt("anthropic")
    assert llm.generate.call_count == 2
    assert llm.generate.call_args_list[0].kwargs["system_prompt"] == expected_system
    assert generation_fixture.prompt.actual_prompt == ANTHROPIC_ACTUAL_PROMPT
    assert generation_fixture.prompt.structure_system_prompt == expected_system
    assert generation_fixture.prompt.structure_prompt_version == expected_version
    assert generation_fixture.prompt.structure_request_id == "response-15"
    assert generation_fixture.prompt.structure_model == "gemini"
    assert generation_fixture.prompt.structure_model_version == "v1"
    usages = (
        test_db.query(ModelCallUsage)
        .filter_by(run_id=generation_fixture.id)
        .order_by(ModelCallUsage.id)
        .all()
    )
    assert [usage.stage for usage in usages] == ["actual_prompt", "assessment"]


def test_anthropic_prompt_provider_failure_is_stage_specific(
    generation_fixture, test_db
):
    generation_fixture.condition.prompt_structure = "anthropic"
    test_db.commit()
    llm = MagicMock()
    llm.generate.side_effect = RuntimeError("structure failed")

    from backend.workers.assessment_worker import run_generation_pipeline

    with patch.object(
        run_generation_pipeline,
        "retry",
        side_effect=Retry("retry scheduled"),
    ):
        with pytest.raises(Retry):
            run_pipeline_synchronously(generation_fixture, test_db, llm)

    test_db.refresh(generation_fixture)
    assert generation_fixture.status == "error"
    assert generation_fixture.error_type == "actual_prompt_provider_error"


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
        llm.generate.side_effect = RuntimeError("temporary provider failure")

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
            "type", "body", "metadata", "revision_options"
        }
        assert "quality_check" not in question_schema["required"]
        assert "quality_check" not in question_schema["properties"]
        assert "metadata" in question_schema["properties"]
        assert "$defs" not in ASSESSMENT_PROVIDER_SCHEMA
        assert "body_segments" not in question_schema["properties"]
        equation_schema = question_schema["properties"]["equations"]["items"]
        assert equation_schema["required"] == ["label", "expression", "location"]
        assert "math" not in equation_schema["properties"]
        assert "model_answer_segments" not in question_schema["properties"]
        usage_calls = (
            test_db.query(ModelCallUsage)
            .filter_by(run_id=generation_fixture.id)
            .order_by(ModelCallUsage.id)
            .all()
        )
        assert [call.stage for call in usage_calls] == [
            "assessment",
            "assessment",
        ]


def test_generation_pipeline_preserves_raw_response_when_parsing_fails(generation_fixture, test_db):
    with (
        patch("backend.workers.assessment_worker.LLMClient") as MockLLM,
        patch("backend.workers.assessment_worker.SessionLocal") as MockSession,
        patch("backend.workers.assessment_worker.redis_client"),
    ):
        MockSession.return_value = test_db
        test_db.close = MagicMock()
        MockLLM.return_value.generate.return_value = LLMResult(
            "not-json", "request-bad", "gemini", "v", "STOP"
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


def test_generation_pipeline_repairs_plain_formula_text_before_docx_creation(
    generation_fixture,
    test_db,
):
    rejected_question = complete_question(
        question_type="short_answer",
        body=(
            "The gas constant is R = 8.314 J/(mol K). "
            "Use [[EQ:entropy_relation]]."
        ),
        model_answer="Use the entropy relation to calculate the result.",
    )
    rejected_question["equations"] = [{
        "label": "entropy_relation",
        "expression": "DeltaS_mix = -R(x_A ln(x_A) + x_B ln(x_B))",
        "location": "question",
    }]
    repaired_question = complete_question(
        question_type="short_answer",
        body=(
            "The gas constant is [[EQ:gas_constant]]. "
            "Use [[EQ:entropy_relation]]."
        ),
        model_answer="Use the entropy relation to calculate the result.",
    )
    repaired_question["equations"] = [
        {
            "label": "gas_constant",
            "expression": "R = 8.314 J/(mol K)",
            "location": "question",
        },
        {
            "label": "entropy_relation",
            "expression": "DeltaS_mix = -R(x_A ln(x_A) + x_B ln(x_B))",
            "location": "question",
        },
    ]
    llm = MagicMock()
    rejected_raw = __import__("json").dumps({"questions": [rejected_question]})
    repaired_raw = __import__("json").dumps({"questions": [repaired_question]})
    llm.generate.side_effect = [
        result(rejected_raw, 20, 8, 28),
        result(repaired_raw, 12, 6, 18),
    ]

    attachments = provider_attachments()
    mock_redis = run_pipeline_synchronously(
        generation_fixture, test_db, llm, attachments=attachments
    )

    test_db.refresh(generation_fixture)
    assert generation_fixture.status == "complete", generation_fixture.error_message
    assert generation_fixture.assessment.raw_response_text == repaired_raw
    assert generation_fixture.assessment.output_hash == sha256_text(repaired_raw)
    assert generation_fixture.assessment.parsed_json["questions"][0]["body"] == (
        repaired_question["body"]
    )
    assert generation_fixture.document_artifact.content == b"PK-generation-docx"
    assert llm.generate.call_count == 2
    expected_error = (
        "1 validation error for AssessmentGenerationResponse\n"
        "questions.0\n"
        "  Value error, body: mathematical expression must use an equation reference"
    )
    repair_call = llm.generate.call_args_list[1]
    assert llm.generate.call_args_list[0].kwargs["attachments"] == attachments
    assert repair_call.kwargs["attachments"] == attachments
    assert repair_call.kwargs["system_prompt"] == (
        build_assessment_repair_system_prompt(
            generation_fixture.prompt.actual_prompt
        )
    )
    assert rejected_raw in repair_call.kwargs["user_message"]
    assert expected_error in repair_call.kwargs["user_message"]
    assert repair_call.kwargs["response_schema"] is ASSESSMENT_PROVIDER_SCHEMA
    usage_stages = [
        usage.stage
        for usage in test_db.query(ModelCallUsage)
        .filter_by(run_id=generation_fixture.id)
        .order_by(ModelCallUsage.id)
        .all()
    ]
    assert usage_stages == ["assessment", "repair"]
    assert generation_fixture.model_call_count == 2
    assert generation_fixture.total_tokens == 46
    mock_redis.evaluation_delay.assert_called_once_with(generation_fixture.id)


def test_generation_pipeline_repairs_cross_location_equation_labels(
    generation_fixture,
    test_db,
):
    rejected_question = complete_question(
        question_type="short_answer",
        body="Calculate [[EQ:g_mix_def]] at [[EQ:temp]].",
        model_answer=(
            "Apply [[EQ:g_mix_def]] at [[EQ:temp]] to obtain "
            "[[EQ:g_mix_result]]."
        ),
    )
    rejected_question["equations"] = [
        {
            "label": "g_mix_def",
            "expression": "G_mix = H_mix - T S_mix",
            "location": "question",
        },
        {
            "label": "temp",
            "expression": "T = 1000 K",
            "location": "question",
        },
        {
            "label": "g_mix_result",
            "expression": "G_mix = -5.76 kJ/mol",
            "location": "solution",
        },
    ]
    repaired_question = complete_question(
        question_type="short_answer",
        body="Calculate [[EQ:g_mix_question]] at [[EQ:temp_question]].",
        model_answer=(
            "Apply [[EQ:g_mix_solution]] at [[EQ:temp_solution]] to obtain "
            "[[EQ:g_mix_result]]."
        ),
    )
    repaired_question["equations"] = [
        {
            "label": "g_mix_question",
            "expression": "G_mix = H_mix - T S_mix",
            "location": "question",
        },
        {
            "label": "temp_question",
            "expression": "T = 1000 K",
            "location": "question",
        },
        {
            "label": "g_mix_solution",
            "expression": "G_mix = H_mix - T S_mix",
            "location": "solution",
        },
        {
            "label": "temp_solution",
            "expression": "T = 1000 K",
            "location": "solution",
        },
        {
            "label": "g_mix_result",
            "expression": "G_mix = -5.76 kJ/mol",
            "location": "solution",
        },
    ]
    rejected_raw = __import__("json").dumps({"questions": [rejected_question]})
    repaired_raw = __import__("json").dumps({"questions": [repaired_question]})
    llm = MagicMock()
    llm.generate.side_effect = [
        result(rejected_raw, 20, 8, 28),
        result(repaired_raw, 12, 6, 18),
    ]

    mock_redis = run_pipeline_synchronously(generation_fixture, test_db, llm)

    test_db.refresh(generation_fixture)
    assert generation_fixture.status == "complete", generation_fixture.error_message
    assert generation_fixture.assessment.raw_response_text == repaired_raw
    assert generation_fixture.document_artifact.content == b"PK-generation-docx"
    assert llm.generate.call_count == 2
    repair_call = llm.generate.call_args_list[1]
    assert (
        "equation labels referenced from both question and solution: "
        "g_mix_def, temp"
        in repair_call.kwargs["user_message"]
    )
    assert "Audit every equation label in every question" in (
        repair_call.kwargs["system_prompt"]
    )
    usage_stages = [
        usage.stage
        for usage in test_db.query(ModelCallUsage)
        .filter_by(run_id=generation_fixture.id)
        .order_by(ModelCallUsage.id)
        .all()
    ]
    assert usage_stages == ["assessment", "repair"]
    assert generation_fixture.model_call_count == 2
    assert generation_fixture.total_tokens == 46
    mock_redis.evaluation_delay.assert_called_once_with(generation_fixture.id)


def test_generation_pipeline_stops_after_one_invalid_repair(
    generation_fixture,
    test_db,
):
    question = complete_question(
        question_type="short_answer",
        body="The gas constant is R = 8.314 J/(mol K).",
        model_answer="Use the supplied value.",
    )
    question["equations"] = []
    rejected_raw = __import__("json").dumps({"questions": [question]})
    llm = MagicMock()
    llm.generate.side_effect = [
        result(rejected_raw, 20, 8, 28),
        result(rejected_raw, 12, 6, 18),
    ]

    mock_redis = run_pipeline_synchronously(generation_fixture, test_db, llm)

    test_db.refresh(generation_fixture)
    assert generation_fixture.status == "error"
    assert generation_fixture.error_type == "assessment_parse_error", (
        generation_fixture.error_message
    )
    assert generation_fixture.assessment.parsed_json is None
    assert generation_fixture.document_artifact is None
    assert llm.generate.call_count == 2
    usage_stages = [
        usage.stage
        for usage in test_db.query(ModelCallUsage)
        .filter_by(run_id=generation_fixture.id)
        .order_by(ModelCallUsage.id)
        .all()
    ]
    assert usage_stages == ["assessment", "repair"]
    assert generation_fixture.model_call_count == 2
    assert generation_fixture.total_tokens == 46
    mock_redis.evaluation_delay.assert_not_called()


def test_invalid_local_actual_prompt_is_rejected_before_persistence(
    generation_fixture, test_db
):
    with (
        patch("backend.workers.assessment_worker.LLMClient") as MockLLM,
        patch("backend.workers.assessment_worker.SessionLocal", return_value=test_db),
        patch("backend.workers.assessment_worker.redis_client"),
        patch(
            "backend.workers.assessment_worker.render_openai_actual_prompt",
            side_effect=ActualPromptValidationError("template invalid"),
        ),
    ):
        test_db.close = MagicMock()
        from backend.workers.assessment_worker import run_generation_pipeline
        run_generation_pipeline(generation_fixture.id)
        test_db.refresh(generation_fixture)
        assert generation_fixture.status == "error"
        assert generation_fixture.error_type == "actual_prompt_validation_error"
        assert generation_fixture.prompt is None
        assert MockLLM.return_value.generate.call_count == 0


def test_openai_generation_provider_failure_is_stage_specific(
    generation_fixture, test_db
):
    with (
        patch("backend.workers.assessment_worker.LLMClient") as MockLLM,
        patch("backend.workers.assessment_worker.SessionLocal", return_value=test_db),
        patch("backend.workers.assessment_worker.redis_client"),
    ):
        test_db.close = MagicMock()
        MockLLM.return_value.generate.side_effect = RuntimeError(
            "generation failed"
        )
        from backend.workers.assessment_worker import run_generation_pipeline
        with patch.object(run_generation_pipeline, "retry", side_effect=RuntimeError("retry scheduled")):
            with pytest.raises(RuntimeError, match="retry scheduled"):
                run_generation_pipeline(generation_fixture.id)
        test_db.refresh(generation_fixture)
        assert generation_fixture.status == "error"
        assert generation_fixture.error_type == "generation_provider_error"


def test_generation_pipeline_ignores_missing_generation(test_db):
    with patch("backend.workers.assessment_worker.SessionLocal") as MockSession:
        MockSession.return_value = test_db
        test_db.close = MagicMock()

        from backend.workers.assessment_worker import run_generation_pipeline

        assert run_generation_pipeline(999_999) is None


def test_missing_generation_deletes_passed_provider_files(test_db):
    attachments = provider_attachments()
    with (
        patch("backend.workers.assessment_worker.SessionLocal", return_value=test_db),
        patch("backend.workers.assessment_worker.LLMClient") as llm_client,
    ):
        test_db.close = MagicMock()
        from backend.workers.assessment_worker import run_generation_pipeline

        run_generation_pipeline.run(
            999_999,
            [attachment.to_dict() for attachment in attachments],
        )

    assert llm_client.return_value.delete_file.call_args_list == [
        call("files/one"),
        call("files/two"),
    ]


def test_openai_pipeline_records_only_assessment_provider_usage(
    generation_fixture, test_db
):
    llm = MagicMock()
    raw_text = __import__("json").dumps(
        {
            "questions": [
                complete_question(
                    question_type="short_answer",
                    body="State equilibrium.",
                    model_answer="Forces and moments balance.",
                )
            ]
        }
    )
    llm.generate.return_value = result(raw_text, 20, 8, 28)

    mock_redis = run_pipeline_synchronously(generation_fixture, test_db, llm)
    calls = (
        test_db.query(ModelCallUsage)
        .filter_by(run_id=generation_fixture.id)
        .order_by(ModelCallUsage.id)
        .all()
    )

    assert [(call.stage, call.total_tokens) for call in calls] == [
        ("assessment", 28),
    ]
    assert llm.generate.call_count == 1
    assert generation_fixture.total_tokens == 28
    assert generation_fixture.document_artifact.content == b"PK-generation-docx"
    mock_redis.evaluation_delay.assert_called_once_with(generation_fixture.id)
    channels = [call.args[0] for call in mock_redis.publish.call_args_list]
    assert f"run:{generation_fixture.id}:progress" in channels


def test_completed_generation_redelivery_preserves_primary_completion(
    generation_fixture, test_db
):
    llm = MagicMock()
    raw_text = __import__("json").dumps(
        {
            "questions": [
                complete_question(
                    question_type="short_answer",
                    body="State equilibrium.",
                    model_answer="Forces and moments balance.",
                )
            ]
        }
    )
    llm.generate.return_value = result(raw_text, 20, 8, 28)
    run_pipeline_synchronously(generation_fixture, test_db, llm)
    completed_at = generation_fixture.completed_at
    artifact_id = generation_fixture.document_artifact.id

    redis_client = run_pipeline_synchronously(generation_fixture, test_db, llm)
    test_db.refresh(generation_fixture)

    assert generation_fixture.status == "complete"
    assert generation_fixture.completed_at == completed_at
    assert generation_fixture.document_artifact.id == artifact_id
    assert llm.generate.call_count == 1
    redis_client.evaluation_delay.assert_called_once_with(generation_fixture.id)


def test_truncated_retry_records_response_usage_once(generation_fixture, test_db):
    llm = MagicMock()
    truncated = TruncatedResponseError(
        result("truncated", 20, 1, 30, finish="MAX_TOKENS")
    )
    llm.generate.side_effect = truncated

    from backend.workers.assessment_worker import run_generation_pipeline

    with patch.object(
        run_generation_pipeline,
        "retry",
        side_effect=Retry("retry scheduled"),
    ):
        with pytest.raises(Retry):
            run_pipeline_synchronously(generation_fixture, test_db, llm)

    calls = (
        test_db.query(ModelCallUsage)
        .filter_by(run_id=generation_fixture.id)
        .order_by(ModelCallUsage.id)
        .all()
    )
    assert [(call.stage, call.total_tokens) for call in calls] == [
        ("assessment", 30),
    ]
    assert generation_fixture.total_tokens == 30


def test_failed_provider_call_is_recorded_without_tokens(generation_fixture, test_db):
    llm = MagicMock()
    llm.generate.side_effect = RuntimeError("provider unavailable")

    from backend.workers.assessment_worker import run_generation_pipeline

    with patch.object(
        run_generation_pipeline,
        "retry",
        side_effect=Retry("retry scheduled"),
    ):
        with pytest.raises(Retry):
            run_pipeline_synchronously(generation_fixture, test_db, llm)

    call = test_db.query(ModelCallUsage).filter_by(run_id=generation_fixture.id).one()
    assert call.stage == "assessment"
    assert call.status == "failed"
    assert call.total_tokens is None


def provider_attachments():
    return [
        ProviderFileAttachment(
            "files/one", "https://files/one", "application/pdf"
        ),
        ProviderFileAttachment(
            "files/two", "https://files/two", "application/pdf"
        ),
    ]


def test_generation_attaches_ordered_pdfs_and_deletes_them_on_success(
    generation_fixture, test_db
):
    llm = MagicMock()
    llm.generate.return_value = result(
        __import__("json").dumps(
            {
                "questions": [
                    complete_question(
                        question_type="short_answer",
                        body="State equilibrium.",
                        model_answer="Forces and moments balance.",
                    )
                ]
            }
        ),
        20,
        8,
        28,
    )
    attachments = provider_attachments()

    run_pipeline_synchronously(
        generation_fixture, test_db, llm, attachments=attachments
    )

    assert llm.generate.call_args.kwargs["attachments"] == attachments
    assert llm.delete_file.call_args_list == [
        call("files/one"),
        call("files/two"),
    ]


def test_anthropic_structure_omits_pdfs_but_assessment_attaches_them(
    generation_fixture, test_db
):
    generation_fixture.condition.prompt_structure = "anthropic"
    test_db.commit()
    llm = MagicMock()
    llm.generate.side_effect = [
        result(ANTHROPIC_ACTUAL_PROMPT, 10, 5, 15),
        result(
            __import__("json").dumps(
                {
                    "questions": [
                        complete_question(
                            question_type="short_answer",
                            body="State equilibrium.",
                            model_answer="Forces and moments balance.",
                        )
                    ]
                }
            ),
            20,
            8,
            28,
        ),
    ]
    attachments = provider_attachments()

    run_pipeline_synchronously(
        generation_fixture, test_db, llm, attachments=attachments
    )

    assert llm.generate.call_args_list[0].kwargs.get("attachments") is None
    assert llm.generate.call_args_list[1].kwargs["attachments"] == attachments


def test_automatic_retry_preserves_provider_files(generation_fixture, test_db):
    llm = MagicMock()
    llm.generate.side_effect = RuntimeError("temporary provider failure")
    attachments = provider_attachments()

    from backend.workers.assessment_worker import run_generation_pipeline

    with patch.object(
        run_generation_pipeline,
        "retry",
        side_effect=Retry("retry scheduled"),
    ):
        with pytest.raises(Retry):
            run_pipeline_synchronously(
                generation_fixture, test_db, llm, attachments=attachments
            )

    llm.delete_file.assert_not_called()


def test_exhausted_retry_deletes_every_provider_file(
    generation_fixture, test_db
):
    llm = MagicMock()
    llm.generate.side_effect = RuntimeError("temporary provider failure")
    llm.delete_file.side_effect = [RuntimeError("delete failed"), None]
    attachments = provider_attachments()

    from backend.workers.assessment_worker import run_generation_pipeline

    with patch.object(
        run_generation_pipeline,
        "retry",
        side_effect=MaxRetriesExceededError(),
    ):
        with pytest.raises(MaxRetriesExceededError):
            run_pipeline_synchronously(
                generation_fixture, test_db, llm, attachments=attachments
            )

    assert llm.delete_file.call_args_list == [
        call("files/one"),
        call("files/two"),
    ]


def test_unavailable_reference_pdf_is_terminal_and_sanitized(
    generation_fixture, test_db
):
    llm = MagicMock()
    llm.generate.side_effect = RuntimeError(
        "provider internal detail: attached file is unavailable"
    )
    attachments = provider_attachments()

    from backend.workers.assessment_worker import run_generation_pipeline

    with patch.object(
        run_generation_pipeline,
        "retry",
        side_effect=AssertionError("unavailable files must not be retried"),
    ):
        run_pipeline_synchronously(
            generation_fixture, test_db, llm, attachments=attachments
        )

    test_db.refresh(generation_fixture)
    assert generation_fixture.error_type == "reference_pdf_unavailable"
    assert generation_fixture.error_message == (
        "An attached reference PDF is unavailable. Upload fresh PDFs and retry."
    )
    assert "provider internal detail" not in generation_fixture.error_message
    assert llm.delete_file.call_args_list == [
        call("files/one"),
        call("files/two"),
    ]
