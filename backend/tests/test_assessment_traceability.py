import json

from backend.models.experiment import Condition, Experiment
from backend.models.run import Assessment, Prompt, Run
from backend.services.assessment_evaluation import persist_assessment_questions
from backend.services.assessment_traceability import enrich_assessment_traceability
from backend.services.reproducibility import canonical_json, sha256_text
from backend.tests.test_worker import complete_assessment_metadata, complete_question


def test_enrichment_uses_real_ids_and_preserves_raw_provider_evidence(test_db):
    experiment = Experiment(
        course="MSE 302",
        topic="Phase stability",
        learning_objectives=["Compare Gibbs energies."],
        assessment_type="short_answer",
        difficulty="medium",
        number_of_questions=1,
    )
    condition = Condition(
        experiment=experiment,
        condition_code="C100",
        prompt_structure="openai",
        condition_label="Baseline",
    )
    run = Run(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="generating",
        model_settings={},
        execution_config={},
    )
    run.prompt = Prompt(
        prompt_structure="openai",
        actual_prompt="Generate one question.",
        structure_prompt_version="template-4",
        actual_prompt_generator_version="11",
    )
    provider_payload = {
        "assessment_metadata": complete_assessment_metadata(),
        "questions": [
            complete_question(
                question_type="short_answer",
                body="Explain phase stability.",
                model_answer="Compare Gibbs energies.",
            )
        ]
    }
    raw = json.dumps(provider_payload, separators=(",", ":"))
    run.assessment = Assessment(
        raw_response_text=raw,
        parsed_json=provider_payload,
        output_hash=sha256_text(raw),
        schema_version="2",
        validation_status="valid",
    )
    test_db.add(run)
    test_db.flush()
    questions = persist_assessment_questions(test_db, run.assessment)

    enriched = enrich_assessment_traceability(test_db, run.assessment)

    assert enriched["traceability"] == {
        "experiment_id": experiment.id,
        "condition_id": condition.id,
        "run_id": run.id,
        "prompt_id": run.prompt.id,
        "prompt_template_version": "template-4",
        "assessment_id": run.assessment.id,
        "assessment_version": 1,
        "assessment_schema_version": "2",
    }
    assert enriched["questions"][0]["traceability"] == {
        "assessment_question_id": questions[0].id,
        "ordinal": 0,
        "assessment_version": 1,
    }
    assert enriched["assessment_metadata"]["prompt_template_id"] == "template-4"
    assert enriched["assessment_metadata"]["actual_prompt_id"] == run.prompt.id
    assert enriched["assessment_metadata"]["output_id"] == run.assessment.id
    assert enriched["assessment_metadata"]["final_question_id"] == [questions[0].id]
    assert run.assessment.raw_response_text == raw
    assert run.assessment.parsed_json_hash == sha256_text(canonical_json(enriched))
