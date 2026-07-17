from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.schemas.evaluation_schema import (
    EvaluationAccessCreate,
    EvaluationAccessDetail,
    EvaluationComparison,
    EvaluationDetail,
    GradingContext,
    HumanEvaluationCreate,
    HumanEvaluationPatch,
)
from backend.schemas.run_schema import RunSummary
from backend.services.assessment_rubric import CRITERION_KEYS
from backend.services.evaluation_service import (
    build_comparison,
    build_grading_context,
    create_human_draft,
    finalize_evaluation,
    list_assessment_evaluations,
    list_assessment_questions,
    record_llm_access,
    reopen_evaluation,
    update_human_draft,
)
from backend.services.run_service import retry_llm_evaluation


router = APIRouter(tags=["evaluations"])


def reviewer_identity() -> str:
    """Single replacement boundary for future authenticated reviewer identity."""

    return settings.local_reviewer_id


def _detail(evaluation) -> EvaluationDetail:
    detail = EvaluationDetail.model_validate(evaluation)
    detail.criteria.sort(
        key=lambda item: CRITERION_KEYS.index(item.criterion_key)
    )
    return detail


@router.get("/assessments/{assessment_id}/questions")
def get_assessment_questions(
    assessment_id: int, db: Session = Depends(get_db)
):
    return list_assessment_questions(db, assessment_id)


@router.get(
    "/assessment-questions/{question_id}/grading-context",
    response_model=GradingContext,
)
def get_grading_context(
    question_id: int,
    db: Session = Depends(get_db),
    reviewer_id: str = Depends(reviewer_identity),
):
    context = build_grading_context(db, question_id, reviewer_id)
    return {
        **context,
        "llm_evaluation": _detail(context["llm_evaluation"]),
        "human_evaluation": _detail(context["human_evaluation"]),
    }


@router.post(
    "/assessments/{assessment_id}/evaluations/llm/retry",
    response_model=RunSummary,
)
def post_llm_evaluation_retry(
    assessment_id: int, db: Session = Depends(get_db)
):
    return retry_llm_evaluation(db, assessment_id)


@router.get(
    "/assessments/{assessment_id}/evaluations",
    response_model=list[EvaluationDetail],
)
def get_assessment_evaluations(
    assessment_id: int, db: Session = Depends(get_db)
):
    return [
        _detail(item)
        for item in list_assessment_evaluations(db, assessment_id)
    ]


@router.post(
    "/assessment-questions/{question_id}/evaluations/human",
    response_model=EvaluationDetail,
)
def post_human_evaluation(
    question_id: int,
    payload: HumanEvaluationCreate,
    db: Session = Depends(get_db),
    reviewer_id: str = Depends(reviewer_identity),
):
    del payload
    return _detail(create_human_draft(db, question_id, reviewer_id))


@router.patch("/evaluations/{evaluation_id}", response_model=EvaluationDetail)
def patch_evaluation(
    evaluation_id: int,
    payload: HumanEvaluationPatch,
    db: Session = Depends(get_db),
    reviewer_id: str = Depends(reviewer_identity),
):
    return _detail(
        update_human_draft(db, evaluation_id, reviewer_id, payload)
    )


@router.post(
    "/evaluations/{evaluation_id}/finalize", response_model=EvaluationDetail
)
def post_finalize_evaluation(
    evaluation_id: int,
    db: Session = Depends(get_db),
    reviewer_id: str = Depends(reviewer_identity),
):
    return _detail(finalize_evaluation(db, evaluation_id, reviewer_id))


@router.post(
    "/evaluations/{evaluation_id}/reopen", response_model=EvaluationDetail
)
def post_reopen_evaluation(
    evaluation_id: int,
    db: Session = Depends(get_db),
    reviewer_id: str = Depends(reviewer_identity),
):
    return _detail(reopen_evaluation(db, evaluation_id, reviewer_id))


@router.post(
    "/evaluations/{evaluation_id}/llm-access",
    response_model=EvaluationAccessDetail,
)
def post_llm_access(
    evaluation_id: int,
    payload: EvaluationAccessCreate,
    db: Session = Depends(get_db),
    reviewer_id: str = Depends(reviewer_identity),
):
    event = record_llm_access(
        db,
        evaluation_id,
        payload.llm_evaluation_id,
        reviewer_id,
    )
    return {
        "first_opened_at": event.opened_at,
        "opened_before_finalization": event.opened_before_finalization,
    }


@router.get(
    "/assessment-questions/{question_id}/evaluation-comparison",
    response_model=EvaluationComparison,
)
def get_evaluation_comparison(
    question_id: int,
    db: Session = Depends(get_db),
    reviewer_id: str = Depends(reviewer_identity),
):
    return build_comparison(db, question_id, reviewer_id)
