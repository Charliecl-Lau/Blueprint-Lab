import json
import redis
from sqlalchemy.orm import Session

from backend.celery_app import celery_app
from backend.config import settings
from backend.database import SessionLocal
from backend.models.assessment import Assessment, PromptGeneration, PlannerOutput, AssessmentGeneration
from backend.models.question import Question, MCQOption, ModelAnswer
from backend.schemas.planner_schema import PlannerResponse
from backend.services.llm_client import LLMClient
from backend.services.prompt_generator import generate_prompt
from backend.services.planner import generate_plan
from backend.services.validator import validate_plan
from backend.services.generator import generate_assessment

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _publish_progress(run_id: int, assessment_id: int, framework: str, control_set_id: int, stage: str):
    event = json.dumps({
        "assessment_id": assessment_id,
        "framework": framework,
        "control_set": control_set_id,
        "stage": stage,
    })
    redis_client.publish(f"run:{run_id}:progress", event)


def _set_status(db: Session, assessment: Assessment, status: str):
    assessment.status = status
    db.commit()


@celery_app.task(bind=True, max_retries=3)
def run_assessment_pipeline(self, assessment_id: int):
    db = SessionLocal()
    try:
        assessment = db.get(Assessment, assessment_id)
        if assessment is None:
            return
        run = assessment.run
        control_set = assessment.control_set

        try:
            llm = LLMClient()

            # --- Stage 1: Prompt Generation (idempotent) ---
            existing_prompt = db.query(PromptGeneration).filter_by(assessment_id=assessment_id).first()
            if existing_prompt:
                prompt_text = existing_prompt.prompt_text
            else:
                _set_status(db, assessment, "prompting")
                _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "prompting")

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

            # --- Stage 2: Planning + Validation (idempotent) ---
            existing_planner = db.query(PlannerOutput).filter_by(assessment_id=assessment_id).first()
            if existing_planner:
                plan = PlannerResponse.model_validate(existing_planner.plan_json)
                validation_passed = existing_planner.validation_passed
            else:
                _set_status(db, assessment, "planning")
                _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "planning")

                plan = generate_plan(llm=llm, generated_prompt=prompt_text)

                _set_status(db, assessment, "validating")
                _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "validating")

                validation = validate_plan(plan, mcq_count=run.mcq_count, long_answer_count=run.long_answer_count)
                validation_passed = validation.passed
                db.add(PlannerOutput(
                    assessment_id=assessment_id,
                    plan_json=plan.model_dump(),
                    validation_passed=validation_passed,
                    validation_errors=validation.errors if not validation_passed else None,
                ))
                db.commit()

            if not validation_passed:
                _set_status(db, assessment, "error")
                _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "error")
                return

            # --- Stage 3: Assessment Generation (idempotent) ---
            existing_gen = db.query(AssessmentGeneration).filter_by(assessment_id=assessment_id).first()
            if existing_gen:
                pass  # questions already inserted; proceed to mark complete
            else:
                _set_status(db, assessment, "generating")
                _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "generating")

                generated = generate_assessment(llm=llm, plan=plan)
                db.add(AssessmentGeneration(assessment_id=assessment_id, raw_json=generated.model_dump()))
                db.commit()

                for order, q in enumerate(generated.questions):
                    question = Question(
                        assessment_id=assessment_id,
                        type=q.type,
                        body=q.body,
                        order=order,
                    )
                    db.add(question)
                    db.flush()

                    if q.type == "mcq":
                        for opt in q.options:
                            db.add(MCQOption(question_id=question.id, body=opt.body, is_correct=opt.is_correct))
                    elif q.type == "long_answer" and q.model_answer:
                        db.add(ModelAnswer(question_id=question.id, body=q.model_answer))

                db.commit()

            _set_status(db, assessment, "complete")
            _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "complete")

        except Exception as exc:
            _set_status(db, assessment, "error")
            _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "error")
            raise self.retry(exc=exc, countdown=10)
    finally:
        db.close()
