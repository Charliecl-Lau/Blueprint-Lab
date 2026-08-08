from backend.config import Settings
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.config import settings
from backend.models import Assessment, DocxAuthoringAttempt, Run
from backend.tests.test_api_runs import _experiment_and_condition


def test_docx_backend_defaults_to_openai_and_supports_manual_opt_in():
    assert Settings(_env_file=None).docx_generation_backend == "luna_direct"
    assert Settings(_env_file=None, docx_generation_backend="luna_direct").docx_generation_backend == "luna_direct"
    assert Settings(_env_file=None, docx_generation_backend="self_hosted_code").docx_generation_backend == "self_hosted_code"
    assert Settings(_env_file=None, docx_generation_backend="agentic_tools").docx_generation_backend == "agentic_tools"


def test_retry_task_dispatches_through_configured_generator_registry(test_db):
    experiment, condition = _experiment_and_condition(test_db)
    run = Run(experiment=experiment, condition=condition, run_number=1, status="rewrite_failed", model_settings={})
    original = Assessment(version=1, kind="original_generation", raw_response_text="{}", parsed_json={"questions": []}, output_hash="a" * 64, schema_version="1")
    run.assessment_versions.append(original); run.canonical_assessment = original
    test_db.add(run); test_db.flush()
    run.docx_authoring_attempts.append(DocxAuthoringAttempt(
        source_assessment_id=original.id, cycle_number=1, attempt_number=1,
        status="requested", provider="google", model="gemini",
        prompt_hash="b" * 64, grounding_hash="c" * 64,
        idempotency_key="retry-key", envelope={}, execution_report={}, validation_report={},
    ))
    test_db.commit(); test_db.close = MagicMock()
    generator = MagicMock()
    generator.generate.return_value = SimpleNamespace(succeeded=True, safe_issue_codes=())
    from backend.workers.assessment_worker import run_docx_rewrite_pipeline
    with (
        patch("backend.workers.assessment_worker.SessionLocal", return_value=test_db),
        patch("backend.workers.assessment_worker.document_generator_registry.get", return_value=generator) as get,
        patch("backend.workers.assessment_worker.redis_client"),
        patch("backend.workers.assessment_worker.run_llm_evaluation_pipeline.delay"),
        patch.object(settings, "docx_generation_backend", "agentic_tools"),
    ):
        run_docx_rewrite_pipeline.run(run.id, "retry-key")
    get.assert_called_once_with("agentic_tools")
    generator.generate.assert_called_once()
