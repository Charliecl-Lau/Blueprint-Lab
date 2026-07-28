from copy import deepcopy

from sqlalchemy.orm import Session

from backend.models.run import Assessment
from backend.schemas.assessment_schema import (
    AssessmentGenerationResponse,
    StoredAssessmentPayload,
)
from backend.services.reproducibility import canonical_json, sha256_text


def provider_payload_from_stored(payload: dict) -> dict:
    candidate = deepcopy(payload)
    candidate.pop("traceability", None)
    for question in candidate.get("questions", []):
        if isinstance(question, dict):
            question.pop("traceability", None)
    return candidate


def question_content_payload(question: dict) -> dict:
    candidate = deepcopy(question)
    candidate.pop("traceability", None)
    return candidate


def enrich_assessment_traceability(
    db: Session, assessment: Assessment
) -> dict:
    db.flush()
    run = assessment.run
    if run is None or assessment.id is None:
        raise ValueError("assessment traceability requires persisted run records")

    provider_payload = provider_payload_from_stored(assessment.parsed_json or {})
    validated = AssessmentGenerationResponse.model_validate(provider_payload).model_dump()
    questions_by_ordinal = {question.ordinal: question for question in assessment.questions}
    if len(questions_by_ordinal) != len(validated["questions"]):
        raise ValueError("assessment traceability requires one persisted row per question")

    enriched = {
        "traceability": {
            "experiment_id": run.experiment_id,
            "condition_id": run.condition_id,
            "run_id": run.id,
            "prompt_id": run.prompt.id if run.prompt else None,
            "prompt_template_version": (
                run.prompt.structure_prompt_version
                if run.prompt else "legacy-unknown"
            ),
            "assessment_id": assessment.id,
            "assessment_version": 1,
            "assessment_schema_version": assessment.schema_version,
        },
        "questions": validated["questions"],
    }
    for ordinal, question_payload in enumerate(enriched["questions"]):
        question = questions_by_ordinal[ordinal]
        question_payload["traceability"] = {
            "assessment_question_id": question.id,
            "ordinal": question.ordinal,
            "assessment_version": question.assessment_version,
        }

    stored = StoredAssessmentPayload.model_validate(enriched).model_dump()
    assessment.parsed_json = stored
    assessment.parsed_json_hash = sha256_text(canonical_json(stored))
    db.flush()
    return stored
