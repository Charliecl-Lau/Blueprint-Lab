from backend.models import Experiment, Run
from backend.schemas.experiment_schema import ExperimentCreate
from backend.services.experiment_service import create_experiment_with_run
from backend.tests.test_api_experiments import valid_payload


def test_creation_service_persists_one_complete_graph(test_db):
    payload = ExperimentCreate(**valid_payload())

    experiment, run, created = create_experiment_with_run(
        test_db, payload, "service-create"
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
        test_db, payload, "same-key"
    )
    second_experiment, second_run, second_created = create_experiment_with_run(
        test_db, payload, "same-key"
    )

    assert first_created is True
    assert second_created is False
    assert second_experiment.id == first_experiment.id
    assert second_run.id == first_run.id
    assert test_db.query(Experiment).count() == 1
    assert test_db.query(Run).count() == 1
