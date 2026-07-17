from copy import deepcopy

import pytest

from backend.models import (
    Assessment,
    Condition,
    DocumentArtifact,
    Evaluation,
    EvaluationCriterion,
    Experiment,
    Run,
)
from backend.config import settings
from backend.schemas.evaluation_schema import HumanCriterionPatch, HumanEvaluationPatch
from backend.services.assessment_evaluation import persist_assessment_questions
from backend.services.assessment_rubric import (
    CRITERION_KEYS,
    RUBRIC_SNAPSHOT,
    RUBRIC_VERSION,
    calculate_evaluation,
)
from backend.services.evaluation_service import (
    EvaluationConflictError,
    IncompleteEvaluationError,
    StaleEvaluationError,
    build_comparison,
    build_grading_context,
    create_human_draft,
    finalize_evaluation,
    record_llm_access,
    reopen_evaluation,
    update_human_draft,
)


def question_payload(ordinal=0):
    return {
        "type": "long_answer",
        "metadata": {
            "question_title": f"Question {ordinal + 1}",
            "question_type": "long_answer",
            "difficulty_level": "advanced",
            "intended_assessment_setting": "Homework",
            "mse202_concepts": ["Equilibrium"],
            "mse302_concepts": ["Chemical potential"],
            "concept_map_bridge": "Connects equilibrium to chemical potential.",
            "materials_science_context": "Alloy phase stability.",
        },
        "body": f"Analyze phase stability for case {ordinal + 1}.",
        "options": [],
        "model_answer": "The lower-Gibbs-energy phase is stable.",
        "revision_options": ["Add numerical data."],
    }


def evaluated_run(test_db, *, question_count=2, llm_scores=None):
    experiment = Experiment(
        course="MSE302",
        topic="Phase stability",
        learning_objectives="Analyze phase stability.",
        assessment_type="long_answer",
        difficulty="advanced",
        number_of_questions=question_count,
    )
    condition = Condition(
        experiment=experiment,
        condition_code="C100",
        prompt_structure="openai",
        factor_configuration={"concept_bridge": True},
        factor_inputs={"concept_bridge": "Equilibrium to chemical potential"},
        condition_label="Concept bridge enabled",
    )
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="complete",
        model="gemini-generation",
        version="generation-v1",
        model_settings={},
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        model_call_count=1,
    )
    payload = {"questions": [question_payload(i) for i in range(question_count)]}
    run.assessment = Assessment(
        raw_response_text="saved",
        parsed_json=deepcopy(payload),
        output_hash="a" * 64,
        schema_version="1",
    )
    run.document_artifact = DocumentArtifact(
        filename="saved.docx",
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        content=b"docx",
    )
    test_db.add(experiment)
    test_db.commit()
    questions = persist_assessment_questions(test_db, run.assessment)
    scores = llm_scores or {key: 5 for key in CRITERION_KEYS}
    calculation = calculate_evaluation(scores)
    for question in questions:
        evaluation = Evaluation.from_run(
            run,
            question=question,
            evaluation_type="llm",
            evaluator_identity=(
                settings.llm_evaluation_model or settings.llm_model
            ),
            evaluation_model=(settings.llm_evaluation_model or settings.llm_model),
            rubric_version=RUBRIC_VERSION,
            rubric_snapshot=RUBRIC_SNAPSHOT,
        )
        evaluation.status = "finalized"
        evaluation.weighted_score = calculation.weighted_score
        evaluation.critical_gate = calculation.critical_gate
        evaluation.overall_decision = calculation.overall_decision
        evaluation.instructor_readiness = calculation.instructor_readiness
        evaluation.criteria = [
            EvaluationCriterion(
                criterion_key=key,
                score=scores[key],
                justification=f"LLM evidence for {key}.",
            )
            for key in CRITERION_KEYS
        ]
        test_db.add(evaluation)
    test_db.commit()
    return run


def score_draft(test_db, draft, scores=None):
    scores = scores or {key: 4 for key in CRITERION_KEYS}
    draft.criteria = [
        EvaluationCriterion(criterion_key=key, score=scores[key])
        for key in CRITERION_KEYS
    ]
    test_db.commit()
    return draft


def test_create_draft_is_idempotent_per_reviewer_and_question(test_db):
    question = evaluated_run(test_db).assessment.questions[0]

    first = create_human_draft(test_db, question.id, "reviewer-a")
    second = create_human_draft(test_db, question.id, "reviewer-a")
    other = create_human_draft(test_db, question.id, "reviewer-b")

    assert first.id == second.id
    assert other.id != first.id
    assert first.evaluation_timestamp is not None


def test_finalize_requires_five_scores_and_recalculates_server_values(test_db):
    question = evaluated_run(test_db).assessment.questions[0]
    draft = create_human_draft(test_db, question.id, "reviewer-a")

    with pytest.raises(IncompleteEvaluationError):
        finalize_evaluation(test_db, draft.id, "reviewer-a")

    draft.weighted_score = 100
    score_draft(test_db, draft)
    finalized = finalize_evaluation(test_db, draft.id, "reviewer-a")

    assert finalized.status == "finalized"
    assert finalized.finalized_at is not None
    assert finalized.weighted_score == 80.0
    assert finalized.overall_decision == "Strong – minor revision"


def test_update_checks_revision_and_only_changes_supplied_fields(test_db):
    question = evaluated_run(test_db).assessment.questions[0]
    draft = create_human_draft(test_db, question.id, "reviewer-a")
    draft.criteria.append(
        EvaluationCriterion(
            criterion_key="technical_correctness",
            score=3,
            comment="Keep this comment.",
        )
    )
    test_db.commit()

    updated = update_human_draft(
        test_db,
        draft.id,
        "reviewer-a",
        HumanEvaluationPatch(
            revision=1,
            criteria=[
                HumanCriterionPatch(
                    criterion_key="technical_correctness", score=4
                )
            ],
        ),
    )

    assert updated.revision == 2
    assert updated.criteria[0].score == 4
    assert updated.criteria[0].comment == "Keep this comment."
    with pytest.raises(StaleEvaluationError):
        update_human_draft(
            test_db,
            draft.id,
            "reviewer-a",
            HumanEvaluationPatch(revision=1, overall_comments="stale"),
        )


def test_reopen_snapshots_finalized_revision_before_unlocking(test_db):
    question = evaluated_run(test_db).assessment.questions[0]
    draft = score_draft(
        test_db,
        create_human_draft(test_db, question.id, "reviewer-a"),
    )
    finalized = finalize_evaluation(test_db, draft.id, "reviewer-a")

    reopened = reopen_evaluation(test_db, finalized.id, "reviewer-a")

    assert reopened.status == "reopened"
    assert reopened.revision == 2
    assert reopened.finalized_at is None
    assert reopened.revisions[0].snapshot["weighted_score"] == 80.0
    assert reopened.revisions[0].snapshot["criteria"][0]["score"] == 4


def test_llm_access_records_first_open_before_finalization_once(test_db):
    question = evaluated_run(test_db).assessment.questions[0]
    human = create_human_draft(test_db, question.id, "reviewer-a")
    llm = next(item for item in question.evaluations if item.evaluation_type == "llm")

    first = record_llm_access(test_db, human.id, llm.id, "reviewer-a")
    second = record_llm_access(test_db, human.id, llm.id, "reviewer-a")

    assert first.id == second.id
    assert first.opened_before_finalization is True


def test_grading_context_uses_experiment_order_and_current_reviewer(test_db):
    run = evaluated_run(test_db, question_count=3)
    first, middle, last = sorted(run.assessment.questions, key=lambda item: item.ordinal)
    other = create_human_draft(test_db, middle.id, "reviewer-b")
    current = create_human_draft(test_db, middle.id, "reviewer-a")

    context = build_grading_context(test_db, middle.id, "reviewer-a")

    assert context["previous_question_id"] == first.id
    assert context["next_question_id"] == last.id
    assert context["human_evaluation"].id == current.id
    assert context["human_evaluation"].id != other.id
    assert context["llm_evaluation"].status == "finalized"
    assert context["question"] == run.assessment.parsed_json["questions"][1]
    assert context["viewer_path"] == f"/experiments/{run.experiment_id}/viewer/{run.id}"


def test_comparison_requires_finalized_human_and_calculates_neutral_metrics(test_db):
    llm_scores = {
        "technical_correctness": 5,
        "course_alignment": 4,
        "blooms_alignment": 3,
        "clarity_solution": 2,
        "materials_context": 1,
    }
    question = evaluated_run(test_db, question_count=1, llm_scores=llm_scores).assessment.questions[0]
    human = create_human_draft(test_db, question.id, "reviewer-a")
    with pytest.raises(EvaluationConflictError):
        build_comparison(test_db, question.id, "reviewer-a")

    human_scores = {
        "technical_correctness": 5,
        "course_alignment": 3,
        "blooms_alignment": 5,
        "clarity_solution": 1,
        "materials_context": 1,
    }
    score_draft(test_db, human, human_scores)
    finalize_evaluation(test_db, human.id, "reviewer-a")

    comparison = build_comparison(test_db, question.id, "reviewer-a")

    assert [item["difference"] for item in comparison["criteria"]] == [0, -1, 2, -1, 0]
    assert comparison["mean_absolute_score_difference"] == 0.8
    assert comparison["exact_agreement_rate"] == 0.4
    assert comparison["agreement_within_one_point"] == 0.8
    assert comparison["largest_disagreement"]["criterion_key"] == "blooms_alignment"
    assert comparison["criteria"][2]["indicator"] == "significant_difference"
