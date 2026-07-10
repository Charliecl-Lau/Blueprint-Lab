import json
import time

import redis
from sqlalchemy.orm import Session

from backend.celery_app import celery_app
from backend.config import settings
from backend.database import SessionLocal
from backend.models.assessment import Assessment, AssessmentGeneration, PlannerOutput, PromptGeneration
from backend.models.experiment import DocumentArtifact, Generation, PromptRecord, utc_now
from backend.models.question import MCQOption, ModelAnswer, Question
from backend.schemas.planner_schema import PlannerResponse
from backend.schemas.experiment_schema import PromptFactors
from backend.services.docx_exporter import build_assessment_docx
from backend.services.generator import generate_questions
from backend.services.llm_client import LLMClient
from backend.services.planner import generate_plan
from backend.services.prompt_generator import generate_prompt
from backend.services.validator import validate_plan


redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _publish_progress(
    experiment_id: int,
    generation_id: int,
    condition_id: int,
    stage: str,
) -> None:
    redis_client.publish(
        f"experiment:{experiment_id}:progress",
        json.dumps(
            {
                "generation_id": generation_id,
                "condition_id": condition_id,
                "stage": stage,
            }
        ),
    )


def _set_status(db: Session, generation: Generation, status: str) -> None:
    generation.status = status
    db.commit()


def _factors_from_condition(condition) -> PromptFactors:
    return PromptFactors(
        course_bridge=condition.course_bridge_enabled,
        few_shot=condition.few_shot_enabled,
        documents=condition.documents_enabled,
    )


@celery_app.task(bind=True, max_retries=3)
def run_generation_pipeline(self, generation_id: int) -> None:
    db = SessionLocal()
    try:
        generation = db.get(Generation, generation_id)
        if generation is None:
            return

        experiment = generation.experiment
        condition = generation.condition
        try:
            llm = LLMClient()
            started = time.perf_counter()

            _set_status(db, generation, "prompting")
            _publish_progress(experiment.id, generation.id, condition.id, "prompting")
            prompt_text = generate_prompt(
                course=experiment.course,
                topic=experiment.topic,
                learning_objectives=experiment.learning_objectives,
                assessment_type=experiment.assessment_type,
                difficulty=experiment.difficulty,
                number_of_questions=experiment.number_of_questions,
                prompt_structure=condition.prompt_structure,
                factors=_factors_from_condition(condition),
            )
            prompt_record = PromptRecord(
                generation_id=generation.id,
                prompt_structure=condition.prompt_structure,
                full_prompt=prompt_text,
            )
            db.add(prompt_record)
            db.commit()
            db.refresh(prompt_record)

            _set_status(db, generation, "generating")
            _publish_progress(experiment.id, generation.id, condition.id, "generating")
            generated = generate_questions(llm=llm, generated_prompt=prompt_text)
            generation.generated_json = generated.model_dump()
            generation.model_name = getattr(llm, "model_name", None)
            generation.model_version = getattr(llm, "model_version", None)
            generation.generation_time_ms = int((time.perf_counter() - started) * 1000)
            generation.completed_at = utc_now()
            db.commit()

            _set_status(db, generation, "documenting")
            _publish_progress(experiment.id, generation.id, condition.id, "documenting")
            docx_bytes = build_assessment_docx(
                assessment_id=generation.id,
                prompt_id=prompt_record.id,
                condition_label=condition.condition_label,
                course=experiment.course,
                topic=experiment.topic,
                questions=generation.generated_json["questions"],
            )
            db.add(
                DocumentArtifact(
                    generation_id=generation.id,
                    filename=f"blueprint-lab-generation-{generation.id}.docx",
                    media_type=(
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                    content=docx_bytes,
                )
            )
            db.commit()

            _set_status(db, generation, "complete")
            _publish_progress(experiment.id, generation.id, condition.id, "complete")
        except Exception as exc:
            db.rollback()
            _set_status(db, generation, "error")
            _publish_progress(experiment.id, generation.id, condition.id, "error")
            raise self.retry(exc=exc, countdown=10)
    finally:
        db.close()


def _publish_legacy_progress(
    run_id: int,
    assessment_id: int,
    framework: str,
    control_set_id: int,
    stage: str,
) -> None:
    redis_client.publish(
        f"run:{run_id}:progress",
        json.dumps(
            {
                "assessment_id": assessment_id,
                "framework": framework,
                "control_set": control_set_id,
                "stage": stage,
            }
        ),
    )


@celery_app.task(bind=True, max_retries=3)
def run_assessment_pipeline(self, assessment_id: int) -> None:
    """Compatibility task for legacy routes retained until their planned removal."""
    db = SessionLocal()
    try:
        assessment = db.get(Assessment, assessment_id)
        if assessment is None:
            return
        run = assessment.run
        control_set = assessment.control_set
        try:
            llm = LLMClient()
            prompt = db.query(PromptGeneration).filter_by(assessment_id=assessment_id).first()
            if prompt is None:
                _set_status(db, assessment, "prompting")
                _publish_legacy_progress(run.id, assessment.id, assessment.framework, control_set.id, "prompting")
                prompt_text = generate_prompt(
                    llm=llm,
                    topic=run.topic,
                    expectations=run.expectations,
                    framework=assessment.framework,
                    personality=control_set.personality,
                    prompt_length=control_set.prompt_length,
                    result_length=control_set.result_length,
                    action_word_count=control_set.action_word_count,
                    mcq_count=run.mcq_count,
                    long_answer_count=run.long_answer_count,
                )
                db.add(PromptGeneration(assessment_id=assessment_id, prompt_text=prompt_text))
                db.commit()
            else:
                prompt_text = prompt.prompt_text

            planner_output = db.query(PlannerOutput).filter_by(assessment_id=assessment_id).first()
            if planner_output is None:
                _set_status(db, assessment, "planning")
                plan = generate_plan(llm=llm, generated_prompt=prompt_text)
                validation = validate_plan(
                    plan,
                    mcq_count=run.mcq_count,
                    long_answer_count=run.long_answer_count,
                )
                planner_output = PlannerOutput(
                    assessment_id=assessment_id,
                    plan_json=plan.model_dump(),
                    validation_passed=validation.passed,
                    validation_errors=validation.errors if not validation.passed else None,
                )
                db.add(planner_output)
                db.commit()
            else:
                plan = PlannerResponse.model_validate(planner_output.plan_json)

            if not planner_output.validation_passed:
                _set_status(db, assessment, "error")
                _publish_legacy_progress(run.id, assessment.id, assessment.framework, control_set.id, "error")
                return

            existing = db.query(AssessmentGeneration).filter_by(assessment_id=assessment_id).first()
            if existing is None:
                _set_status(db, assessment, "generating")
                generated = generate_questions(llm=llm, generated_prompt=json.dumps(plan.model_dump()))
                db.add(AssessmentGeneration(assessment_id=assessment_id, raw_json=generated.model_dump()))
                for order, item in enumerate(generated.questions):
                    question = Question(
                        assessment_id=assessment_id,
                        type=item.type,
                        body=item.body,
                        order=order,
                    )
                    db.add(question)
                    db.flush()
                    for option in item.options:
                        db.add(MCQOption(question_id=question.id, body=option.body, is_correct=option.is_correct))
                    if item.type == "long_answer" and item.model_answer:
                        db.add(ModelAnswer(question_id=question.id, body=item.model_answer))
                db.commit()

            _set_status(db, assessment, "complete")
            _publish_legacy_progress(run.id, assessment.id, assessment.framework, control_set.id, "complete")
        except Exception as exc:
            db.rollback()
            _set_status(db, assessment, "error")
            _publish_legacy_progress(run.id, assessment.id, assessment.framework, control_set.id, "error")
            raise self.retry(exc=exc, countdown=10)
    finally:
        db.close()
