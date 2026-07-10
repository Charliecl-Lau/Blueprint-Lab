from backend.models.experiment import (
    Condition,
    DocumentArtifact,
    Experiment,
    Generation,
    PromptRecord,
    RubricResult,
)


def test_experiment_condition_generation_metadata_round_trip(test_db):
    experiment = Experiment(
        course="ENGR 101",
        topic="Free-body diagrams",
        learning_objectives="Apply equilibrium equations to planar systems.",
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=3,
    )
    test_db.add(experiment)
    test_db.flush()

    condition = Condition(
        experiment_id=experiment.id,
        prompt_structure="openai",
        concept_bridge_enabled=True,
        few_shot_enabled=False,
        reference_content_enabled=True,
        reasoning_guidance_enabled=False,
        factor_inputs={"concept_bridge": "Vectors", "reference_content": "SI units"},
        condition_label="ConceptBridge=ON; FewShot=OFF; ReferenceContent=ON; ReasoningGuidance=OFF",
    )
    test_db.add(condition)
    test_db.flush()

    generation = Generation(
        experiment_id=experiment.id,
        condition_id=condition.id,
        status="complete",
        model_name="gemini",
        model_version="gemini-2.0-flash",
        generation_time_ms=1200,
        generated_json={"questions": []},
    )
    test_db.add(generation)
    test_db.flush()

    prompt = PromptRecord(
        generation_id=generation.id,
        prompt_structure="openai",
        full_prompt="Generate an assessment.",
    )
    artifact = DocumentArtifact(
        generation_id=generation.id,
        filename="assessment.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=b"docx-bytes",
    )
    rubric = RubricResult(
        generation_id=generation.id,
        reviewer="Reviewer A",
        rubric_score=4.5,
        comments="Strong alignment.",
    )
    test_db.add_all([prompt, artifact, rubric])
    test_db.commit()

    saved = test_db.get(Generation, generation.id)
    assert saved.condition.condition_label == "ConceptBridge=ON; FewShot=OFF; ReferenceContent=ON; ReasoningGuidance=OFF"
    assert saved.prompt_record.full_prompt == "Generate an assessment."
    assert saved.document_artifact.filename == "assessment.docx"
    assert saved.rubric_results[0].rubric_score == 4.5
