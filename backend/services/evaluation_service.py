from copy import deepcopy
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import (
    Assessment,
    AssessmentQuestion,
    Evaluation,
    EvaluationAccessEvent,
    EvaluationCriterion,
    EvaluationRevision,
    Run,
)
from backend.models.experiment import utc_now
from backend.schemas.evaluation_schema import HumanEvaluationPatch
from backend.services.assessment_rubric import (
    CRITERION_KEYS,
    RUBRIC_SNAPSHOT,
    RUBRIC_VERSION,
    calculate_evaluation,
)


class EvaluationServiceError(RuntimeError):
    status_code = 409


class EvaluationNotFoundError(EvaluationServiceError):
    status_code = 404


class EvaluationConflictError(EvaluationServiceError):
    pass


class StaleEvaluationError(EvaluationConflictError):
    pass


class IncompleteEvaluationError(EvaluationServiceError):
    status_code = 422


def _evaluation_model() -> str:
    return settings.llm_evaluation_model or settings.llm_model


def _question(db: Session, question_id: int) -> AssessmentQuestion:
    question = db.get(AssessmentQuestion, question_id)
    if question is None:
        raise EvaluationNotFoundError("Assessment question not found")
    return question


def _evaluation(db: Session, evaluation_id: int, *, lock=False) -> Evaluation:
    statement = select(Evaluation).where(Evaluation.id == evaluation_id)
    if lock and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    evaluation = db.scalar(statement)
    if evaluation is None:
        raise EvaluationNotFoundError("Evaluation not found")
    return evaluation


def _require_human_owner(evaluation: Evaluation, reviewer_id: str) -> None:
    if evaluation.evaluation_type != "human":
        raise EvaluationConflictError("LLM evaluations are read-only")
    if evaluation.evaluator_identity != reviewer_id:
        raise EvaluationConflictError("Evaluation belongs to another reviewer")


def _current_llm_evaluation(question: AssessmentQuestion) -> Optional[Evaluation]:
    candidates = [
        item
        for item in question.evaluations
        if item.evaluation_type == "llm"
        and item.evaluator_identity == _evaluation_model()
        and item.rubric_version == RUBRIC_VERSION
        and item.status == "finalized"
    ]
    return max(candidates, key=lambda item: (item.attempt, item.id or 0), default=None)


def _human_evaluation(
    question: AssessmentQuestion, reviewer_id: str
) -> Optional[Evaluation]:
    candidates = [
        item
        for item in question.evaluations
        if item.evaluation_type == "human"
        and item.evaluator_identity == reviewer_id
    ]
    return max(candidates, key=lambda item: (item.attempt, item.id or 0), default=None)


def _score_map(evaluation: Evaluation) -> Optional[dict[str, int]]:
    values = {
        item.criterion_key: item.score
        for item in evaluation.criteria
        if item.criterion_key in CRITERION_KEYS and item.score is not None
    }
    if set(values) != set(CRITERION_KEYS):
        return None
    return values


def _apply_calculation(
    evaluation: Evaluation, scores: Optional[dict[str, int]]
) -> None:
    if scores is None:
        evaluation.weighted_score = None
        evaluation.critical_gate = None
        evaluation.overall_decision = None
        evaluation.instructor_readiness = None
        return
    calculation = calculate_evaluation(scores)
    evaluation.weighted_score = calculation.weighted_score
    evaluation.critical_gate = calculation.critical_gate
    evaluation.overall_decision = calculation.overall_decision
    evaluation.instructor_readiness = calculation.instructor_readiness


def create_human_draft(
    db: Session, question_id: int, reviewer_id: str
) -> Evaluation:
    question = _question(db, question_id)
    existing = _human_evaluation(question, reviewer_id)
    if existing is not None:
        return existing
    run = question.assessment.run
    if run.status != "complete" or _current_llm_evaluation(question) is None:
        raise EvaluationConflictError(
            "Human grading is unavailable until LLM evaluation completes"
        )

    draft = Evaluation.from_run(
        run,
        question=question,
        evaluation_type="human",
        evaluator_identity=reviewer_id,
        rubric_version=RUBRIC_VERSION,
        rubric_snapshot=RUBRIC_SNAPSHOT,
    )
    draft.status = "draft"
    draft.evaluation_timestamp = utc_now()
    db.add(draft)
    try:
        db.commit()
        db.refresh(draft)
        return draft
    except IntegrityError:
        db.rollback()
        winner = _human_evaluation(_question(db, question_id), reviewer_id)
        if winner is None:
            raise
        return winner


def update_human_draft(
    db: Session,
    evaluation_id: int,
    reviewer_id: str,
    payload: HumanEvaluationPatch,
) -> Evaluation:
    evaluation = _evaluation(db, evaluation_id, lock=True)
    _require_human_owner(evaluation, reviewer_id)
    if evaluation.status not in {"draft", "reopened"}:
        raise EvaluationConflictError("Finalized evaluations are locked")
    if payload.revision != evaluation.revision:
        raise StaleEvaluationError(
            "Evaluation was updated elsewhere; reload before saving"
        )

    criteria = {item.criterion_key: item for item in evaluation.criteria}
    if payload.criteria is not None:
        for patch in payload.criteria:
            criterion = criteria.get(patch.criterion_key)
            if criterion is None:
                criterion = EvaluationCriterion(
                    criterion_key=patch.criterion_key,
                )
                evaluation.criteria.append(criterion)
                criteria[patch.criterion_key] = criterion
            fields = patch.model_fields_set
            if "score" in fields:
                criterion.score = patch.score
            if "comment" in fields:
                criterion.comment = patch.comment
            if "suggested_modification" in fields:
                criterion.suggested_modification = patch.suggested_modification
            if "issue_flags" in fields:
                criterion.issue_flags = list(patch.issue_flags or [])

    fields = payload.model_fields_set
    if "highest_priority_issue" in fields:
        evaluation.highest_priority_issue = payload.highest_priority_issue
    if "overall_comments" in fields:
        evaluation.overall_comments = payload.overall_comments
    if "recommended_action" in fields:
        evaluation.recommended_action = payload.recommended_action

    evaluation.revision += 1
    db.flush()
    _apply_calculation(evaluation, _score_map(evaluation))
    db.commit()
    db.refresh(evaluation)
    return evaluation


def finalize_evaluation(
    db: Session, evaluation_id: int, reviewer_id: str
) -> Evaluation:
    evaluation = _evaluation(db, evaluation_id, lock=True)
    _require_human_owner(evaluation, reviewer_id)
    if evaluation.status == "finalized":
        return evaluation
    if evaluation.status not in {"draft", "reopened"}:
        raise EvaluationConflictError("Evaluation cannot be finalized")
    scores = _score_map(evaluation)
    if scores is None:
        raise IncompleteEvaluationError(
            "A score from 1 through 5 is required for every rubric dimension"
        )

    _apply_calculation(evaluation, scores)
    now = utc_now()
    evaluation.status = "finalized"
    evaluation.finalized_at = now
    db.commit()
    db.refresh(evaluation)
    return evaluation


def _snapshot(evaluation: Evaluation) -> dict:
    return {
        "revision": evaluation.revision,
        "status": evaluation.status,
        "weighted_score": evaluation.weighted_score,
        "critical_gate": evaluation.critical_gate,
        "overall_decision": evaluation.overall_decision,
        "instructor_readiness": evaluation.instructor_readiness,
        "highest_priority_issue": evaluation.highest_priority_issue,
        "overall_comments": evaluation.overall_comments,
        "recommended_action": evaluation.recommended_action,
        "evaluation_timestamp": (
            evaluation.evaluation_timestamp.isoformat()
            if evaluation.evaluation_timestamp
            else None
        ),
        "finalized_at": (
            evaluation.finalized_at.isoformat() if evaluation.finalized_at else None
        ),
        "criteria": [
            {
                "criterion_key": item.criterion_key,
                "score": item.score,
                "comment": item.comment,
                "suggested_modification": item.suggested_modification,
                "issue_flags": list(item.issue_flags or []),
            }
            for item in sorted(
                evaluation.criteria,
                key=lambda item: CRITERION_KEYS.index(item.criterion_key),
            )
        ],
    }


def reopen_evaluation(
    db: Session, evaluation_id: int, reviewer_id: str
) -> Evaluation:
    evaluation = _evaluation(db, evaluation_id, lock=True)
    _require_human_owner(evaluation, reviewer_id)
    if evaluation.status != "finalized":
        raise EvaluationConflictError("Only a finalized evaluation can be reopened")

    db.add(
        EvaluationRevision(
            evaluation=evaluation,
            revision=evaluation.revision,
            snapshot=_snapshot(evaluation),
            created_by=reviewer_id,
        )
    )
    evaluation.status = "reopened"
    evaluation.revision += 1
    evaluation.finalized_at = None
    db.commit()
    db.refresh(evaluation)
    return evaluation


def record_llm_access(
    db: Session,
    human_evaluation_id: int,
    llm_evaluation_id: int,
    reviewer_id: str,
) -> EvaluationAccessEvent:
    human = _evaluation(db, human_evaluation_id)
    _require_human_owner(human, reviewer_id)
    llm = _evaluation(db, llm_evaluation_id)
    if (
        llm.evaluation_type != "llm"
        or llm.status != "finalized"
        or llm.question_id != human.question_id
    ):
        raise EvaluationConflictError(
            "LLM evaluation does not match this human evaluation"
        )
    existing = db.scalar(
        select(EvaluationAccessEvent).where(
            EvaluationAccessEvent.human_evaluation_id == human.id,
            EvaluationAccessEvent.llm_evaluation_id == llm.id,
            EvaluationAccessEvent.reviewer_id == reviewer_id,
        )
    )
    if existing is not None:
        return existing

    event = EvaluationAccessEvent(
        human_evaluation=human,
        llm_evaluation=llm,
        reviewer_id=reviewer_id,
        opened_before_finalization=human.status != "finalized",
    )
    db.add(event)
    try:
        db.commit()
        db.refresh(event)
        return event
    except IntegrityError:
        db.rollback()
        winner = db.scalar(
            select(EvaluationAccessEvent).where(
                EvaluationAccessEvent.human_evaluation_id == human_evaluation_id,
                EvaluationAccessEvent.llm_evaluation_id == llm_evaluation_id,
                EvaluationAccessEvent.reviewer_id == reviewer_id,
            )
        )
        if winner is None:
            raise
        return winner


def list_assessment_questions(db: Session, assessment_id: int) -> list[dict]:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise EvaluationNotFoundError("Assessment not found")
    questions = sorted(assessment.questions, key=lambda item: item.ordinal)
    payloads = assessment.parsed_json.get("questions", []) if assessment.parsed_json else []
    return [
        {
            "id": question.id,
            "assessment_id": assessment.id,
            "ordinal": question.ordinal,
            "assessment_version": question.assessment_version,
            "content_hash": question.content_hash,
            "question": deepcopy(payloads[question.ordinal]),
        }
        for question in questions
    ]


def list_assessment_evaluations(
    db: Session, assessment_id: int
) -> list[Evaluation]:
    if db.get(Assessment, assessment_id) is None:
        raise EvaluationNotFoundError("Assessment not found")
    return list(
        db.scalars(
            select(Evaluation)
            .where(Evaluation.assessment_id == assessment_id)
            .order_by(Evaluation.question_id, Evaluation.evaluation_type, Evaluation.id)
        ).all()
    )


def _ordered_experiment_questions(db: Session, run: Run) -> list[AssessmentQuestion]:
    questions = list(
        db.scalars(
            select(AssessmentQuestion)
            .join(Assessment, AssessmentQuestion.assessment_id == Assessment.id)
            .join(Run, Assessment.run_id == Run.id)
            .where(Run.experiment_id == run.experiment_id)
            .order_by(Run.created_at, Run.id, AssessmentQuestion.ordinal)
        ).all()
    )
    return [
        item
        for item in questions
        if item.assessment.run.status == "complete"
        and _current_llm_evaluation(item) is not None
    ]


def build_grading_context(
    db: Session, question_id: int, reviewer_id: str
) -> dict:
    question = _question(db, question_id)
    run = question.assessment.run
    llm = _current_llm_evaluation(question)
    if run.status != "complete" or llm is None:
        raise EvaluationConflictError(
            "Grading is unavailable until LLM evaluation completes"
        )
    human = create_human_draft(db, question_id, reviewer_id)
    ordered = _ordered_experiment_questions(db, run)
    current_index = next(
        (index for index, item in enumerate(ordered) if item.id == question.id),
        None,
    )
    if current_index is None:
        raise EvaluationConflictError("Question is not available for grading")
    payload = question.assessment.parsed_json["questions"][question.ordinal]
    return {
        "experiment_id": run.experiment_id,
        "run_id": run.id,
        "assessment_id": question.assessment_id,
        "question_id": question.id,
        "question": deepcopy(payload),
        "rubric": deepcopy(RUBRIC_SNAPSHOT),
        "llm_evaluation": llm,
        "human_evaluation": human,
        "previous_question_id": (
            ordered[current_index - 1].id if current_index > 0 else None
        ),
        "next_question_id": (
            ordered[current_index + 1].id
            if current_index + 1 < len(ordered)
            else None
        ),
        "viewer_path": f"/experiments/{run.experiment_id}/viewer/{run.id}",
    }


def build_comparison(db: Session, question_id: int, reviewer_id: str) -> dict:
    question = _question(db, question_id)
    human = _human_evaluation(question, reviewer_id)
    llm = _current_llm_evaluation(question)
    if human is None or human.status != "finalized":
        raise EvaluationConflictError(
            "Comparison is unavailable until human evaluation is finalized"
        )
    if llm is None:
        raise EvaluationConflictError("Completed LLM evaluation is unavailable")
    human_scores = _score_map(human)
    llm_scores = _score_map(llm)
    if human_scores is None or llm_scores is None:
        raise EvaluationConflictError("Completed evaluation scores are unavailable")

    criteria = []
    for key in CRITERION_KEYS:
        difference = human_scores[key] - llm_scores[key]
        absolute = abs(difference)
        criteria.append(
            {
                "criterion_key": key,
                "human_score": human_scores[key],
                "llm_score": llm_scores[key],
                "difference": difference,
                "absolute_difference": absolute,
                "indicator": (
                    "agreement"
                    if absolute == 0
                    else "minor_difference"
                    if absolute == 1
                    else "significant_difference"
                ),
            }
        )
    largest = max(criteria, key=lambda item: item["absolute_difference"])
    count = len(criteria)
    return {
        "criteria": criteria,
        "mean_absolute_score_difference": round(
            sum(item["absolute_difference"] for item in criteria) / count, 2
        ),
        "exact_agreement_rate": round(
            sum(item["absolute_difference"] == 0 for item in criteria) / count, 2
        ),
        "agreement_within_one_point": round(
            sum(item["absolute_difference"] <= 1 for item in criteria) / count, 2
        ),
        "largest_disagreement": largest,
        "human_weighted_score": human.weighted_score,
        "llm_weighted_score": llm.weighted_score,
        "weighted_score_difference": round(
            human.weighted_score - llm.weighted_score, 1
        ),
        "human_overall_decision": human.overall_decision,
        "llm_overall_decision": llm.overall_decision,
        "decision_difference": human.overall_decision != llm.overall_decision,
    }
