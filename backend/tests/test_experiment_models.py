from backend.models import Assessment, Condition, DocumentArtifact, Experiment, Generation, PromptRecord
from backend.models.run import RubricResult


def test_experiment_table_uses_objective_array_without_obsolete_research_columns():
    columns = Experiment.__table__.columns

    assert columns["learning_objectives"].type.python_type is dict
    assert {"description", "topic_area", "research_question"}.isdisjoint(
        columns.keys()
    )


def test_experiment_condition_metadata_round_trip(test_db):
    experiment = Experiment(
        name="Free-body diagram study",
        status="active",
        course="ENGR 101",
        topic="Free-body diagrams",
        learning_objectives=["Apply equilibrium equations to planar systems."],
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=3,
        cognitive_demand="evaluate_create",
        additional_instruction="Use one laboratory scenario.",
    )
    condition = Condition(
        experiment=experiment,
        condition_code="C100",
        prompt_structure="openai",
        concept_bridge_enabled=True,
        few_shot_enabled=False,
        reference_content_enabled=True,
        reasoning_guidance_enabled=False,
        bloom_level_enabled=True,
        factor_configuration={"concept_bridge": "Vectors"},
        factor_inputs={"reference_content": "SI units"},
        condition_label="Concept bridge and reference content",
    )
    test_db.add(experiment)
    test_db.commit()

    saved = test_db.get(Condition, condition.id)
    assert saved.experiment.name == "Free-body diagram study"
    assert saved.condition_code == "C100"
    assert saved.factor_configuration == {"concept_bridge": "Vectors"}
    assert saved.experiment.cognitive_demand == "evaluate_create"
    assert saved.experiment.additional_instruction == "Use one laboratory scenario."


def test_legacy_generation_children_round_trip(test_db):
    experiment = Experiment(
        name="Compatibility study",
        status="active",
        course="ENGR 101",
        topic="Free-body diagrams",
        learning_objectives=["Apply equilibrium equations."],
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=3,
    )
    condition = Condition(
        experiment=experiment,
        condition_code="C100",
        prompt_structure="openai",
        condition_label="Baseline",
    )
    generation = Generation(
        experiment=experiment,
        condition=condition,
        run_number=1,
        status="complete",
        provider="google",
        model_name="gemini-2.0-flash",
        model_version="2026-01",
        generation_time_ms=1200,
    )
    generation.assessment = Assessment(
        raw_response_text='{"questions": []}',
        parsed_json={"questions": []},
        output_hash="c" * 64,
        schema_version="1",
    )
    generation.prompt_record = PromptRecord(
        prompt_structure="openai",
        full_prompt="Generate an assessment.",
        prompt_hash="a" * 64,
    )
    generation.document_artifact = DocumentArtifact(
        filename="assessment.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=b"docx-bytes",
        content_hash="b" * 64,
    )
    generation.rubric_results.append(
        RubricResult(reviewer="Reviewer A", rubric_score=4.5, comments="Strong alignment.")
    )
    test_db.add(experiment)
    test_db.commit()

    saved = test_db.get(Generation, generation.id)
    assert saved.condition.condition_code == "C100"
    assert saved.provider == "google"
    assert saved.model_name == "gemini-2.0-flash"
    assert saved.prompt_record.full_prompt == "Generate an assessment."
    assert saved.document_artifact.filename == "assessment.docx"
    assert saved.rubric_results[0].rubric_score == 4.5
