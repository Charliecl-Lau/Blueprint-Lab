import json
from copy import deepcopy
from typing import Callable
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Assessment, AssessmentQuestion, Evaluation, EvaluationCriterion
from backend.models.experiment import utc_now
from backend.schemas.evaluation_schema import LLMEvaluationResponse
from backend.services.assessment_rubric import (
    CRITERION_KEYS,
    RUBRIC_SNAPSHOT,
    RUBRIC_VERSION,
    calculate_evaluation,
)
from backend.services.llm_client import LLMClient, TruncatedResponseError
from backend.services.reproducibility import canonical_json, sha256_text
from backend.services.usage_tracking import record_model_call


EVALUATION_SYSTEM_PROMPT = """You are an independent assessment-quality evaluator.
Analyze the immutable saved assessment against the supplied rubric. Return one score from 1 through 5 for every rubric criterion and provide concise evidence for each score. Treat scores 2 and 4 as performance between the stated 1, 3, and 5 anchors.

You must not rewrite, edit, repair, regenerate, or otherwise modify the generated question or model answer. Suggested changes belong only in the evaluation feedback fields. Base every conclusion on the saved content and research context supplied in the user message.
"""

EVALUATION_PROGRESS_MESSAGES = (
    "Preparing generated assessment for evaluation",
    "Evaluating technical correctness and solvability",
    "Evaluating course alignment and concept bridge",
    "Evaluating Bloom's taxonomy alignment",
    "Evaluating clarity and solution quality",
    "Evaluating materials science relevance",
    "Calculating weighted score",
    "Saving LLM evaluation results",
)


class EvaluationValidationError(RuntimeError):
    """Raised when a saved assessment cannot produce a valid evaluation."""


def _saved_question(assessment: Assessment, ordinal: int) -> dict:
    parsed = assessment.parsed_json
    questions = parsed.get("questions") if isinstance(parsed, dict) else None
    if not isinstance(questions, list) or ordinal < 0 or ordinal >= len(questions):
        raise EvaluationValidationError("saved assessment question is unavailable")
    question = questions[ordinal]
    if not isinstance(question, dict):
        raise EvaluationValidationError("saved assessment question is invalid")
    return question


def persist_assessment_questions(
    db: Session, assessment: Assessment
) -> list[AssessmentQuestion]:
    parsed = assessment.parsed_json
    questions = parsed.get("questions") if isinstance(parsed, dict) else None
    if not isinstance(questions, list):
        raise EvaluationValidationError(
            "validated assessment must contain a questions array"
        )

    existing = {item.ordinal: item for item in assessment.questions}
    persisted = []
    for ordinal, question_payload in enumerate(questions):
        if not isinstance(question_payload, dict):
            raise EvaluationValidationError(
                f"validated assessment question {ordinal} must be an object"
            )
        content_hash = sha256_text(canonical_json(question_payload))
        question = existing.get(ordinal)
        if question is None:
            question = AssessmentQuestion(
                assessment=assessment,
                ordinal=ordinal,
                assessment_version=1,
                content_hash=content_hash,
            )
            db.add(question)
        elif question.content_hash != content_hash:
            raise EvaluationValidationError(
                "saved assessment content hash changed; create a new assessment version"
            )
        persisted.append(question)

    db.flush()
    return persisted


def build_evaluation_input(run, question: AssessmentQuestion) -> str:
    assessment = run.assessment
    if assessment is None or question.assessment_id != assessment.id:
        raise EvaluationValidationError("question does not belong to the saved assessment")

    saved_question = _saved_question(assessment, question.ordinal)
    content_hash = sha256_text(canonical_json(saved_question))
    if content_hash != question.content_hash:
        raise EvaluationValidationError(
            "saved assessment content hash does not match the evaluation version"
        )

    experiment = run.experiment
    condition = run.condition
    payload = {
        "evaluation_instruction": (
            "Analyze and score this saved assessment. You must not modify the question "
            "or model answer; place proposed changes only in suggested feedback fields."
        ),
        "saved_assessment": {
            "assessment_id": assessment.id,
            "question_id": question.id,
            "assessment_version": question.assessment_version,
            "content_hash": question.content_hash,
            "question": deepcopy(saved_question),
            "model_answer": deepcopy(saved_question.get("model_answer")),
        },
        "experiment_requirements": {
            "course": experiment.course,
            "topic": experiment.topic,
            "learning_objectives": experiment.learning_objectives,
            "assessment_type": experiment.assessment_type,
            "difficulty": experiment.difficulty,
            "number_of_questions": experiment.number_of_questions,
            "estimated_time_minutes": experiment.estimated_time_minutes,
            "cognitive_demand": experiment.cognitive_demand,
            "additional_instruction": experiment.additional_instruction,
        },
        "prompt_design_factors": {
            "configuration": deepcopy(condition.factor_configuration),
            "inputs": deepcopy(condition.factor_inputs),
        },
        "prompt_provenance": {
            "prompt_template_id": (
                run.prompt.structure_prompt_version if run.prompt else None
            ),
            "actual_prompt_id": str(run.prompt.id) if run.prompt else None,
            "output_id": str(assessment.id),
            "generation_model": run.model,
            "generation_model_version": run.version,
        },
        "rubric": deepcopy(RUBRIC_SNAPSHOT),
    }
    return canonical_json(payload)


def _next_attempt(db: Session, question_id: int, evaluator_identity: str) -> int:
    previous = db.scalar(
        select(func.max(Evaluation.attempt)).where(
            Evaluation.question_id == question_id,
            Evaluation.evaluation_type == "llm",
            Evaluation.evaluator_identity == evaluator_identity,
        )
    )
    return (previous or 0) + 1


def _mark_failed(db: Session, evaluation: Evaluation) -> None:
    evaluation.status = "failed"
    evaluation.evaluation_timestamp = utc_now()
    db.add(evaluation)
    db.commit()


def evaluate_question(
    db: Session,
    run,
    question: AssessmentQuestion,
    llm: LLMClient,
    progress: Callable[[str], None],
) -> Evaluation:
    evaluator_identity = getattr(llm, "model", None) or "llm-evaluator"
    evaluation = Evaluation.from_run(
        run,
        question=question,
        evaluation_type="llm",
        evaluator_identity=evaluator_identity,
        rubric_version=RUBRIC_VERSION,
        rubric_snapshot=RUBRIC_SNAPSHOT,
        evaluation_model=evaluator_identity,
        attempt=_next_attempt(db, question.id, evaluator_identity),
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    progress(EVALUATION_PROGRESS_MESSAGES[0])
    try:
        user_message = build_evaluation_input(run, question)
    except EvaluationValidationError:
        _mark_failed(db, evaluation)
        raise
    call_id = str(uuid4())
    try:
        result = llm.generate(
            system_prompt=EVALUATION_SYSTEM_PROMPT,
            user_message=user_message,
            model_settings={"temperature": 0},
            response_schema=LLMEvaluationResponse,
        )
    except TruncatedResponseError as exc:
        record_model_call(
            db,
            run=run,
            call_id=call_id,
            stage="evaluation",
            attempt=evaluation.attempt,
            result=exc.result,
        )
        _mark_failed(db, evaluation)
        raise EvaluationValidationError(
            "LLM evaluation provider response was incomplete"
        ) from exc
    except Exception as exc:
        record_model_call(
            db,
            run=run,
            call_id=call_id,
            stage="evaluation",
            attempt=evaluation.attempt,
            failed=True,
        )
        _mark_failed(db, evaluation)
        raise EvaluationValidationError("LLM evaluation provider request failed") from exc

    record_model_call(
        db,
        run=run,
        call_id=call_id,
        stage="evaluation",
        attempt=evaluation.attempt,
        result=result,
    )

    for message in EVALUATION_PROGRESS_MESSAGES[1:6]:
        progress(message)

    try:
        structured = LLMEvaluationResponse.model_validate_json(result.raw_text)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        _mark_failed(db, evaluation)
        raise EvaluationValidationError(
            "LLM evaluation returned an invalid structured response"
        ) from exc

    progress(EVALUATION_PROGRESS_MESSAGES[6])
    criterion_results = {item.criterion_key: item for item in structured.criteria}
    calculation = calculate_evaluation(
        {key: criterion_results[key].score for key in CRITERION_KEYS}
    )

    evaluation.criteria = [
        EvaluationCriterion(
            criterion_key=key,
            score=criterion_results[key].score,
            justification=criterion_results[key].justification,
            strengths=list(criterion_results[key].strengths),
            weaknesses=list(criterion_results[key].weaknesses),
            suggested_improvements=list(
                criterion_results[key].suggested_improvements
            ),
            suggested_modifications=list(
                criterion_results[key].suggested_modifications
            ),
        )
        for key in CRITERION_KEYS
    ]
    evaluation.weighted_score = calculation.weighted_score
    evaluation.critical_gate = calculation.critical_gate
    evaluation.overall_decision = calculation.overall_decision
    evaluation.instructor_readiness = calculation.instructor_readiness
    evaluation.major_strengths = list(structured.major_strengths)
    evaluation.major_weaknesses = list(structured.major_weaknesses)
    evaluation.highest_priority_revision = structured.highest_priority_revision
    evaluation.recommended_action = structured.recommended_instructor_action
    evaluation.evaluation_model = result.model_name
    evaluation.evaluation_model_version = result.model_version
    evaluation.status = "finalized"
    evaluation.evaluation_timestamp = utc_now()
    evaluation.finalized_at = evaluation.evaluation_timestamp
    progress(EVALUATION_PROGRESS_MESSAGES[7])
    db.commit()
    db.refresh(evaluation)
    return evaluation
