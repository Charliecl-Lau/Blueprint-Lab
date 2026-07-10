from unittest.mock import patch

from backend.models.experiment import Condition, DocumentArtifact, Experiment, Generation, PromptRecord


def make_generation(test_db):
    experiment = Experiment(
        course="ENGR 101",
        topic="Statics",
        learning_objectives="Solve equilibrium problems.",
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=1,
    )
    test_db.add(experiment)
    test_db.flush()
    condition = Condition(
        experiment_id=experiment.id,
        prompt_structure="openai",
        concept_bridge_enabled=False,
        few_shot_enabled=False,
        reference_content_enabled=False,
        reasoning_guidance_enabled=False,
        factor_inputs={},
        condition_label="ConceptBridge=OFF; FewShot=OFF; ReferenceContent=OFF; ReasoningGuidance=OFF",
    )
    test_db.add(condition)
    test_db.flush()
    generation = Generation(
        experiment_id=experiment.id,
        condition_id=condition.id,
        status="complete",
        model_name="gemini",
        model_version="v1",
        generation_time_ms=20,
        generated_json={"questions": []},
    )
    test_db.add(generation)
    test_db.flush()
    test_db.add(PromptRecord(generation_id=generation.id, prompt_structure="openai", full_prompt="Prompt"))
    test_db.add(DocumentArtifact(
        generation_id=generation.id,
        filename="generation.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=b"docx-bytes",
    ))
    test_db.commit()
    return generation


def test_get_generation_detail(client, test_db):
    generation = make_generation(test_db)

    response = client.get(f"/generations/{generation.id}")

    assert response.status_code == 200
    assert response.json()["prompt_text"] == "Prompt"
    assert response.json()["condition"]["condition_label"] == "ConceptBridge=OFF; FewShot=OFF; ReferenceContent=OFF; ReasoningGuidance=OFF"


def test_export_docx_returns_word_artifact(client, test_db):
    generation = make_generation(test_db)

    response = client.get(f"/generations/{generation.id}/export-docx")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert response.content == b"docx-bytes"


def test_regenerate_clears_artifacts_and_generation_metadata(client, test_db):
    generation = make_generation(test_db)

    with patch("backend.api.generations.run_generation_pipeline.delay") as delay:
        response = client.post(f"/generations/{generation.id}/regenerate")

    assert response.status_code == 200
    test_db.refresh(generation)
    assert generation.status == "pending"
    assert generation.generated_json is None
    assert generation.model_name is None
    assert generation.model_version is None
    assert generation.generation_time_ms is None
    assert generation.prompt_record is None
    assert generation.document_artifact is None
    delay.assert_called_once_with(generation.id)


def test_generation_routes_return_404_for_missing_records(client):
    assert client.get("/generations/999999").status_code == 404
    assert client.post("/generations/999999/regenerate").status_code == 404
    assert client.get("/generations/999999/export-docx").status_code == 404
