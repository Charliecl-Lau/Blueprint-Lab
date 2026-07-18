import pytest

from backend.models import Experiment, Run
from backend.schemas.experiment_schema import ExperimentCreate
from backend.services.experiment_service import (
    ExperimentValidationError,
    create_experiment_with_run,
)
from backend.tests.test_api_experiments import valid_payload


def test_creation_service_persists_one_complete_graph(test_db):
    payload = ExperimentCreate(**valid_payload())

    experiment, run, created = create_experiment_with_run(
        test_db, payload, "service-create", ["reference.pdf"]
    )

    assert created is True
    assert experiment.conditions[0].id == run.condition_id
    assert experiment.runs == [run]
    assert (
        run.input_tokens,
        run.output_tokens,
        run.total_tokens,
        run.model_call_count,
    ) == (0, 0, 0, 0)
    assert test_db.query(Experiment).count() == 1
    assert test_db.query(Run).count() == 1


def test_creation_service_reuses_idempotency_winner(test_db):
    payload = ExperimentCreate(**valid_payload())
    first_experiment, first_run, first_created = create_experiment_with_run(
        test_db, payload, "same-key", ["reference.pdf"]
    )
    second_experiment, second_run, second_created = create_experiment_with_run(
        test_db, payload, "same-key", ["ignored-on-duplicate.pdf"]
    )

    assert first_created is True
    assert second_created is False
    assert second_experiment.id == first_experiment.id
    assert second_run.id == first_run.id
    assert test_db.query(Experiment).count() == 1
    assert test_db.query(Run).count() == 1


def test_reference_content_requires_filename_metadata(test_db):
    payload = ExperimentCreate(**valid_payload())

    with pytest.raises(ExperimentValidationError) as raised:
        create_experiment_with_run(test_db, payload, "pdf-required", [])

    assert raised.value.issues[0].field == "reference_pdfs"


def test_service_persists_ordered_filenames_without_factor_text(test_db):
    raw_payload = valid_payload()
    raw_payload["factor_inputs"].pop("reference_content", None)
    payload = ExperimentCreate(**raw_payload)

    _, run, created = create_experiment_with_run(
        test_db,
        payload,
        "pdfs",
        ["one.pdf", "two.pdf"],
    )

    assert created is True
    assert run.reference_pdf_filenames == ["one.pdf", "two.pdf"]
    assert "reference_content" not in run.condition.factor_inputs


def test_service_rejects_pdf_names_when_factor_is_disabled(test_db):
    raw_payload = valid_payload()
    raw_payload["factors"]["reference_content"] = False
    raw_payload["factor_inputs"].pop("reference_content", None)
    payload = ExperimentCreate(**raw_payload)

    with pytest.raises(ExperimentValidationError) as raised:
        create_experiment_with_run(test_db, payload, "disabled", ["one.pdf"])

    assert raised.value.issues[0].field == "reference_pdfs"
