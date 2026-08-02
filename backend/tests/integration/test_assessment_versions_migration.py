import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from backend.tests.integration.test_research_migration import alembic_config


def test_assessment_versions_migration_preserves_evidence_and_enforces_ownership(
    postgres_url,
):
    engine = create_engine(postgres_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))

    config = alembic_config(postgres_url)
    command.upgrade(config, "20260717_01")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO experiments
                  (id,name,description,topic_area,research_question,status,course,
                   topic,learning_objectives,assessment_type,difficulty,
                   number_of_questions,estimated_time_minutes,created_at,updated_at,
                   cognitive_demand,additional_instruction)
                VALUES
                  (1,'Study','','MSE','Question','active','MSE302','Phase equilibria',
                   'Analyze stability','long_answer','advanced',1,30,now(),now(),
                   'analyze_evaluate',NULL)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO conditions
                  (id,experiment_id,condition_code,prompt_structure,
                   concept_bridge_enabled,few_shot_enabled,reference_content_enabled,
                   reasoning_guidance_enabled,bloom_level_enabled,factor_configuration,
                   factor_inputs,condition_label,created_at)
                VALUES
                  (1,1,'C100','openai',false,false,false,false,false,'{}','{}',
                   'Baseline',now())
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO runs
                  (id,experiment_id,condition_id,run_number,status,model_settings,created_at)
                VALUES (1,1,1,1,'complete','{}',now()),
                       (2,1,1,2,'complete','{}',now())
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO assessments
                  (id,run_id,raw_response_text,parsed_json,output_hash,schema_version,created_at)
                VALUES
                  (10,1,'original','{"questions": []}',
                   'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','1',now()),
                  (20,2,'other','{"questions": []}',
                   'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','1',now())
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO document_artifacts
                  (id,run_id,filename,media_type,content,content_hash,created_at)
                VALUES
                  (30,1,'saved.docx',
                   'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                   decode('504b','hex'),
                   'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',now())
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO assessment_questions
                  (id,assessment_id,ordinal,assessment_version,content_hash,created_at)
                VALUES
                  (40,10,0,1,
                   'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',now())
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO evaluations
                  (id,experiment_id,condition_id,run_id,assessment_id,question_id,
                   assessment_version,assessment_content_hash,evaluation_type,
                   evaluator_identity,attempt,rubric_version,rubric_snapshot,
                   prompt_design_factors,major_strengths,major_weaknesses,status,
                   revision,created_at,updated_at)
                VALUES
                  (50,1,1,1,10,40,1,
                   'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
                   'human','reviewer',1,'1','{}','{}','[]','[]','finalized',1,
                   now(),now())
                """
            )
        )

    command.upgrade(config, "20260802_01")

    inspector = inspect(engine)
    assert {"version", "kind", "source_assessment_id", "canonicalized_at"}.issubset(
        {item["name"] for item in inspector.get_columns("assessments")}
    )
    with engine.connect() as connection:
        migrated = connection.execute(
            text(
                """
                SELECT a.id,a.run_id,a.version,a.kind,a.output_hash,a.parsed_json_hash,
                       r.canonical_assessment_id,r.status,d.assessment_id,d.content,
                       q.assessment_id AS question_assessment_id,
                       e.assessment_id AS evaluation_assessment_id
                FROM assessments a
                JOIN runs r ON r.id=a.run_id
                LEFT JOIN document_artifacts d ON d.run_id=r.id
                LEFT JOIN assessment_questions q ON q.assessment_id=a.id
                LEFT JOIN evaluations e ON e.assessment_id=a.id
                WHERE a.id=10
                """
            )
        ).mappings().one()

    assert migrated["version"] == 1
    assert migrated["kind"] == "original_generation"
    assert migrated["canonical_assessment_id"] == 10
    assert migrated["assessment_id"] == 10
    assert migrated["question_assessment_id"] == 10
    assert migrated["evaluation_assessment_id"] == 10
    assert migrated["output_hash"] == "a" * 64
    assert migrated["parsed_json_hash"] is not None
    assert bytes(migrated["content"]) == b"PK"
    assert migrated["status"] == "complete"

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE runs SET canonical_assessment_id=20 WHERE id=1")
            )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO document_artifacts
                      (run_id,assessment_id,filename,media_type,content,content_hash,created_at)
                    VALUES
                      (1,20,'cross.docx','application/octet-stream',decode('50','hex'),
                       'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
                       now())
                    """
                )
            )
