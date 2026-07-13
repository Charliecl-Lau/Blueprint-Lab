import json
from unittest.mock import MagicMock, patch

from backend.models.experiment import Condition, Experiment
from backend.schemas.run_schema import SourceBinding
from backend.services.llm_client import LLMResult
from backend.services.run_service import create_run, retry_run
from backend.services.source_documents import create_source_document
from backend.tests.test_worker import ACTUAL_PROMPT, complete_question


def test_research_workflow_preserves_independent_runs_and_source_snapshot(test_db):
    uploaded_bytes = b"Use SI units and preserve this exact source snapshot."
    source = create_source_document(
        test_db,
        name="Course syllabus",
        document_type="course_syllabus",
        version="2026.1",
        filename="syllabus.txt",
        media_type="text/plain",
        content=uploaded_bytes,
        description="Research fixture",
    )
    experiment = Experiment(
        course="ENGR 101",
        topic="Statics",
        learning_objectives="Solve equilibrium problems.",
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=1,
    )
    test_db.add(experiment)
    test_db.flush()
    condition = Condition(
        experiment_id=experiment.id,
        condition_code="C101",
        prompt_structure="openai",
        factor_inputs={"reference_content": source.extracted_text},
        condition_label="ReferenceContent=ON",
        reference_content_enabled=True,
    )
    test_db.add(condition)
    test_db.commit()

    run_1 = create_run(
        test_db,
        condition.id,
        [SourceBinding(source_document_id=source.id, role="course_syllabus", ordinal=0)],
    )
    assessment_responses = [
        json.dumps({"questions": [complete_question(
            question_type="long_answer",
            body="Explain equilibrium.",
            model_answer="Forces balance.",
        )]}),
        json.dumps({"questions": [complete_question(
            question_type="long_answer",
            body="Explain moment equilibrium.",
            model_answer="Moments balance.",
        )]}),
    ]

    def provider_result(*_args, **_kwargs):
        if provider_result.call_number % 2 == 0:
            raw_text = ACTUAL_PROMPT
        else:
            raw_text = assessment_responses.pop(0)
        provider_result.call_number += 1
        return LLMResult(raw_text, "request-id", "gemini", "test-version", "STOP")
    provider_result.call_number = 0

    with (
        patch("backend.workers.assessment_worker.SessionLocal", return_value=test_db),
        patch("backend.workers.assessment_worker.LLMClient") as mock_client,
        patch("backend.workers.assessment_worker.redis_client"),
    ):
        test_db.close = MagicMock()
        mock_client.return_value.generate.side_effect = provider_result
        from backend.workers.assessment_worker import run_generation_pipeline

        run_generation_pipeline(run_1.id)
        run_2 = retry_run(test_db, run_1.id)
        run_generation_pipeline(run_2.id)

    test_db.refresh(run_1)
    test_db.refresh(run_2)
    assert run_1.id != run_2.id
    assert run_1.run_number == 1
    assert run_2.run_number == 2
    assert run_1.prompt.prompt_hash
    assert run_2.prompt.prompt_hash
    assert run_1.assessment.raw_response_text
    assert run_2.assessment.raw_response_text
    assert run_1.source_documents[0].source_document.content == uploaded_bytes
    assert run_1.document_artifact.content
    assert run_2.document_artifact.content
    assert mock_client.return_value.generate.call_count == 4
    source_text = uploaded_bytes.decode()
    calls = mock_client.return_value.generate.call_args_list
    assert all(source_text not in calls[index].kwargs["user_message"] for index in (0, 2))
    assert all(source_text in calls[index].kwargs["user_message"] for index in (1, 3))
