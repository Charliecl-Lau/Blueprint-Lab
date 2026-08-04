import pytest
from sqlalchemy.exc import IntegrityError

from backend.models import DocxToolAction, DocxToolIteration, DocxToolSession
from backend.tests.test_api_runs import _experiment_and_condition
from backend.models import Assessment, Run


def test_agentic_models_enforce_session_and_action_uniqueness(test_db):
    experiment, condition = _experiment_and_condition(test_db)
    run = Run(experiment=experiment, condition=condition, run_number=1, status="pending", model_settings={})
    source = Assessment(version=1, kind="original_generation", raw_response_text="{}", parsed_json={"questions": []}, output_hash="a" * 64, schema_version="1")
    run.assessment_versions.append(source); run.canonical_assessment = source
    test_db.add(run); test_db.flush()
    session = DocxToolSession(run_id=run.id, source_assessment_id=source.id, cycle_number=1, provider="google", model="gemini", status="pending", content_catalog_hash="b" * 64, design_contract_hash="c" * 64, workspace_revision=0, maximum_revisions=2, idempotency_key="same")
    test_db.add(session); test_db.flush()
    iteration = DocxToolIteration(session_id=session.id, iteration_number=0, kind="design", input_workspace_hash="d" * 64)
    test_db.add(iteration); test_db.flush()
    test_db.add(DocxToolAction(session_id=session.id, iteration_id=iteration.id, sequence_number=0, operation_id="op", tool_name="create_document", validated_arguments={}, status="succeeded", before_workspace_hash="e" * 64, after_workspace_hash="f" * 64, duration_ms=0))
    test_db.commit()
    test_db.add(DocxToolAction(session_id=session.id, iteration_id=iteration.id, sequence_number=1, operation_id="op", tool_name="create_document", validated_arguments={}, status="succeeded", before_workspace_hash="e" * 64, after_workspace_hash="f" * 64, duration_ms=0))
    with pytest.raises(IntegrityError): test_db.commit()
    test_db.rollback()
