from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from backend.models import (
    Assessment,
    AssessmentQuestion,
    Condition,
    Evaluation,
    EvaluationAccessEvent,
    EvaluationCriterion,
    EvaluationRevision,
    Experiment,
    Prompt,
    Run,
)
from backend.services.assessment_rubric import RUBRIC_SNAPSHOT, RUBRIC_VERSION


@pytest.fixture
def generation_fixture(test_db):
    experiment = Experiment(
        name="Thermodynamics quality study",
        description="Compare assessment quality.",
        topic_area="Materials thermodynamics",
        research_question="How does prompt design affect quality?",
        status="active",
        course="MSE302",
        topic="Phase equilibria",
        learning_objectives="Connect chemical potential to phase stability.",
        assessment_type="long_answer",
        difficulty="advanced",
        number_of_questions=1,
        cognitive_demand="analyze_evaluate",
    )
    condition = Condition(
        experiment=experiment,
        condition_code="C101",
        prompt_structure="openai",
        concept_bridge_enabled=True,
        factor_configuration={"concept_bridge": True},
        factor_inputs={"concept_bridge": "MSE202 equilibrium to MSE302 phase stability"},
        condition_label="Concept bridge enabled",
    )
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="complete",
        provider="google",
        model="gemini-3.1-flash-lite",
        version="2026-07-01",
    )
    run.prompt = Prompt(
        prompt_structure="openai",
        structure_system_prompt="System",
        structure_input="Input",
        actual_prompt="Generate one phase-equilibria assessment.",
        actual_prompt_hash="a" * 64,
        structure_prompt_version="rubric-template-v1",
        actual_prompt_generator_version="generator-v1",
        generation_context="Context",
        generation_envelope_hash="b" * 64,
    )
    run.assessment = Assessment(
        raw_response_text='{"questions": []}',
        parsed_json={"questions": []},
        output_hash="c" * 64,
        schema_version="1.0",
    )
    test_db.add(experiment)
    test_db.commit()
    return run


def make_question(run, suffix="d"):
    return AssessmentQuestion(
        assessment_id=run.assessment.id,
        ordinal=0,
        assessment_version=1,
        content_hash=suffix * 64,
    )


def make_evaluation(run, question, evaluator_identity="reviewer-a", evaluation_type="human"):
    return Evaluation.from_run(
        run,
        question=question,
        evaluation_type=evaluation_type,
        evaluator_identity=evaluator_identity,
        rubric_version=RUBRIC_VERSION,
        rubric_snapshot=RUBRIC_SNAPSHOT,
    )


def test_question_and_multiple_evaluators_are_stored_without_overwrite(test_db, generation_fixture):
    question = make_question(generation_fixture)
    test_db.add(question)
    test_db.flush()
    first = make_evaluation(generation_fixture, question, "reviewer-a")
    second = make_evaluation(generation_fixture, question, "reviewer-b")
    test_db.add_all([first, second])
    test_db.commit()

    assert {item.evaluator_identity for item in question.evaluations} == {
        "reviewer-a",
        "reviewer-b",
    }


def test_evaluation_copies_research_provenance_at_creation(test_db, generation_fixture):
    question = make_question(generation_fixture)
    evaluation = make_evaluation(generation_fixture, question)
    test_db.add(evaluation)
    test_db.commit()

    assert evaluation.experiment_id == generation_fixture.experiment_id
    assert evaluation.condition_id == generation_fixture.condition_id
    assert evaluation.run_id == generation_fixture.id
    assert evaluation.assessment_id == generation_fixture.assessment.id
    assert evaluation.prompt_template_id == "rubric-template-v1"
    assert evaluation.actual_prompt_id == str(generation_fixture.prompt.id)
    assert evaluation.output_id == str(generation_fixture.assessment.id)
    assert evaluation.generation_model == "gemini-3.1-flash-lite"
    assert evaluation.generation_model_version == "2026-07-01"
    assert evaluation.prompt_design_factors == {
        "configuration": {"concept_bridge": True},
        "inputs": {"concept_bridge": "MSE202 equilibrium to MSE302 phase stability"},
    }


def test_criterion_enforces_unique_key_per_evaluation(test_db, generation_fixture):
    evaluation = make_evaluation(generation_fixture, make_question(generation_fixture))
    evaluation.criteria.extend(
        [
            EvaluationCriterion(criterion_key="technical_correctness", score=3),
            EvaluationCriterion(criterion_key="technical_correctness", score=4),
        ]
    )
    test_db.add(evaluation)

    with pytest.raises(IntegrityError):
        test_db.commit()


@pytest.mark.parametrize("score", [0, 6])
def test_criterion_enforces_score_scale(test_db, generation_fixture, score):
    evaluation = make_evaluation(generation_fixture, make_question(generation_fixture))
    evaluation.criteria.append(
        EvaluationCriterion(criterion_key="technical_correctness", score=score)
    )
    test_db.add(evaluation)

    with pytest.raises(IntegrityError):
        test_db.commit()


def test_question_content_hash_is_not_globally_unique(test_db, generation_fixture):
    first = make_question(generation_fixture, "e")
    first.ordinal = 0
    second = make_question(generation_fixture, "e")
    second.ordinal = 1
    test_db.add_all([first, second])
    test_db.commit()

    assert first.content_hash == second.content_hash


def test_revision_and_first_access_records_are_preserved(test_db, generation_fixture):
    question = make_question(generation_fixture)
    human = make_evaluation(generation_fixture, question, "reviewer-a", "human")
    llm = make_evaluation(generation_fixture, question, "gemini-evaluator", "llm")
    revision = EvaluationRevision(
        evaluation=human,
        revision=1,
        snapshot={"status": "finalized", "weighted_score": 80.0},
        created_by="reviewer-a",
    )
    event = EvaluationAccessEvent(
        human_evaluation=human,
        llm_evaluation=llm,
        reviewer_id="reviewer-a",
        opened_at=datetime.now(timezone.utc),
        opened_before_finalization=True,
    )
    test_db.add_all([revision, event])
    test_db.commit()

    assert human.revisions[0].snapshot["weighted_score"] == 80.0
    assert human.llm_access_events[0].opened_before_finalization is True


def test_new_pipeline_statuses_and_progress_fields_round_trip(test_db, generation_fixture):
    generation_fixture.status = "evaluating_quality"
    generation_fixture.viewer_ready_at = datetime.now(timezone.utc)
    generation_fixture.progress_message = "Evaluating technical correctness and solvability"
    test_db.commit()
    test_db.refresh(generation_fixture)

    assert generation_fixture.status == "evaluating_quality"
    assert generation_fixture.viewer_ready_at is not None
    assert generation_fixture.progress_message == "Evaluating technical correctness and solvability"
