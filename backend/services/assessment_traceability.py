from copy import deepcopy

from sqlalchemy.orm import Session

from backend.models.run import Assessment
from backend.schemas.assessment_schema import (
    AssessmentGenerationResponse,
    StoredAssessmentPayload,
)
from backend.services.reproducibility import canonical_json, sha256_text


def _legacy_assessment_metadata(run, questions: list[dict]) -> dict:
    experiment = run.experiment
    question_metadata = [item.get("metadata") or {} for item in questions]

    def unique_values(key: str) -> list[str]:
        values = []
        for item in question_metadata:
            candidate = item.get(key)
            candidates = candidate if isinstance(candidate, list) else [candidate]
            for value in candidates:
                if value is not None and value not in values:
                    values.append(value)
        return values

    factors = []
    for key, label in (
        ("concept_bridge_enabled", "Concept Bridge"),
        ("few_shot_enabled", "Few-shot Examples"),
        ("reference_content_enabled", "Reference Content"),
        ("reasoning_guidance_enabled", "Reasoning Guidance"),
    ):
        if getattr(run.condition, key, False):
            factors.append(label)
    bridges = unique_values("concept_map_bridge")
    contexts = unique_values("materials_science_context")
    return {
        "question_title": f"{experiment.topic} assessment",
        "course": experiment.course,
        "topic": experiment.topic,
        "question_type": experiment.assessment_type,
        "number_of_questions": len(questions),
        "difficulty_level": experiment.difficulty,
        "cognitive_demand": experiment.cognitive_demand,
        "intended_assessment_setting": "Instructor question bank",
        "mse202_concepts": unique_values("mse202_concepts") or [experiment.topic],
        "mse302_concepts": unique_values("mse302_concepts") or [experiment.topic],
        "concept_map_bridge": "; ".join(bridges) if bridges else None,
        "materials_science_context": "; ".join(contexts) or experiment.topic,
        "numerical_computation": "Not specified in legacy assessment data",
        "estimated_time": f"{experiment.estimated_time_minutes} minutes",
        "learning_objectives": list(experiment.learning_objectives),
        "prompt_design_factors": factors,
        "additional_instructions": experiment.additional_instruction,
    }


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
        "assessment_metadata": validated["assessment_metadata"] or _legacy_assessment_metadata(
            run, validated["questions"]
        ),
        "questions": validated["questions"],
    }
    metadata = enriched["assessment_metadata"]
    metadata["prompt_template_id"] = enriched["traceability"][
        "prompt_template_version"
    ]
    metadata["actual_prompt_id"] = enriched["traceability"]["prompt_id"]
    metadata["output_id"] = assessment.id
    for ordinal, question_payload in enumerate(enriched["questions"]):
        question = questions_by_ordinal[ordinal]
        question_payload["traceability"] = {
            "assessment_question_id": question.id,
            "ordinal": question.ordinal,
            "assessment_version": question.assessment_version,
        }
    metadata["final_question_id"] = [
        question_payload["traceability"]["assessment_question_id"]
        for question_payload in enriched["questions"]
    ]

    stored = StoredAssessmentPayload.model_validate(enriched).model_dump()
    assessment.parsed_json = stored
    assessment.parsed_json_hash = sha256_text(canonical_json(stored))
    db.flush()
    return stored
