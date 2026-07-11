import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import JSON, bindparam, create_engine, text


ROOT = Path(__file__).resolve().parents[3]


def alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    return config


def test_revision_renders_offline_postgresql_sql():
    env = os.environ | {"DATABASE_URL": "postgresql+psycopg://unused:unused@localhost/unused"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ALTER TABLE generations RENAME TO runs" in result.stdout
    assert "CREATE TABLE assessments" in result.stdout
    assert "populated by the online migration" not in result.stdout
    prompt_update = result.stdout.index("UPDATE prompts SET prompt_hash")
    prompt_not_null = result.stdout.index("ALTER TABLE prompts ALTER COLUMN prompt_hash SET NOT NULL")
    artifact_update = result.stdout.index("UPDATE document_artifacts SET content_hash")
    artifact_not_null = result.stdout.index("ALTER TABLE document_artifacts ALTER COLUMN content_hash SET NOT NULL")
    assert prompt_update < prompt_not_null
    assert artifact_update < artifact_not_null
    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto" in result.stdout
    assert "assessment backfill evidence validation failed" in result.stdout
    assert "duplicate prompt_records for run IDs" in result.stdout
    assert "duplicate document_artifacts for run IDs" in result.stdout


def test_upgrade_preserves_exact_legacy_evidence(postgres_url):
    engine = create_engine(postgres_url)
    legacy_json = {"questions": [{"text": "What is stress?", "points": 4}]}
    second_json = {"questions": [{"text": "What is strain?", "points": 6}]}
    artifact = b"PK\x03\x04legacy-docx-bytes"
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        connection.execute(text("""
            CREATE TABLE experiments (id SERIAL PRIMARY KEY, course VARCHAR NOT NULL, topic VARCHAR NOT NULL,
              learning_objectives VARCHAR NOT NULL, assessment_type VARCHAR NOT NULL, difficulty VARCHAR NOT NULL,
              number_of_questions INTEGER NOT NULL, estimated_time_minutes INTEGER NOT NULL, created_at TIMESTAMP NOT NULL);
            CREATE TABLE conditions (id SERIAL PRIMARY KEY, experiment_id INTEGER NOT NULL REFERENCES experiments(id),
              prompt_structure VARCHAR NOT NULL, concept_bridge_enabled BOOLEAN NOT NULL, few_shot_enabled BOOLEAN NOT NULL,
              reference_content_enabled BOOLEAN NOT NULL, reasoning_guidance_enabled BOOLEAN NOT NULL,
              factor_inputs JSON NOT NULL, condition_label VARCHAR NOT NULL);
            CREATE TABLE generations (id SERIAL PRIMARY KEY, experiment_id INTEGER NOT NULL REFERENCES experiments(id),
              condition_id INTEGER NOT NULL REFERENCES conditions(id), status VARCHAR, model_name VARCHAR,
              model_version VARCHAR, generation_time_ms INTEGER, generated_json JSON, created_at TIMESTAMP NOT NULL,
              completed_at TIMESTAMP);
            CREATE TABLE prompt_records (id SERIAL PRIMARY KEY, generation_id INTEGER NOT NULL REFERENCES generations(id),
              prompt_structure VARCHAR NOT NULL, full_prompt VARCHAR NOT NULL, created_at TIMESTAMP NOT NULL);
            CREATE TABLE document_artifacts (id SERIAL PRIMARY KEY, generation_id INTEGER NOT NULL REFERENCES generations(id),
              filename VARCHAR NOT NULL, media_type VARCHAR NOT NULL, content BYTEA NOT NULL, created_at TIMESTAMP NOT NULL);
            CREATE TABLE rubric_results (id SERIAL PRIMARY KEY, generation_id INTEGER NOT NULL REFERENCES generations(id),
              reviewer VARCHAR, rubric_score FLOAT, comments VARCHAR, created_at TIMESTAMP NOT NULL);
        """))
        connection.execute(text("INSERT INTO experiments VALUES (1,'ME 101','Stress','Calculate stress','quiz','medium',1,30,now())"))
        connection.execute(text("INSERT INTO conditions VALUES (1,1,'structured',true,false,false,true,'{}','baseline')"))
        connection.execute(text("INSERT INTO conditions VALUES (2,1,'structured',false,true,false,false,'{}','alternate')"))
        insert_generation = text("INSERT INTO generations VALUES (1,1,1,'complete','gemma','v1',123,:payload,now(),now())").bindparams(bindparam("payload", type_=JSON))
        connection.execute(insert_generation, {"payload": legacy_json})
        insert_more = text("""
          INSERT INTO generations (id,experiment_id,condition_id,status,model_name,model_version,generation_time_ms,generated_json,created_at,completed_at)
          VALUES (:id,1,:condition,'complete','gemma','v1',124,:payload,:created,:created)
        """).bindparams(bindparam("payload", type_=JSON))
        connection.execute(insert_more, {"id": 2, "condition": 1, "payload": second_json, "created": "2026-01-01 00:00:00"})
        connection.execute(insert_more, {"id": 3, "condition": 2, "payload": None, "created": "2026-01-02 00:00:00"})
        connection.execute(text("INSERT INTO prompt_records VALUES (1,1,'structured','FINAL LEGACY PROMPT',now())"))
        connection.execute(text("INSERT INTO document_artifacts VALUES (1,1,'quiz.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document',:content,now())"), {"content": artifact})
        connection.execute(text("INSERT INTO rubric_results VALUES (1,2,'reviewer-a',4.5,'preserve me',now())"))

    command.upgrade(alembic_config(postgres_url), "head")
    with engine.connect() as connection:
        runs = connection.execute(text("SELECT id, run_number, seed FROM runs ORDER BY id")).all()
        prompt = connection.execute(text("SELECT final_prompt, generator_version FROM prompts WHERE run_id=1")).one()
        assessment = connection.execute(text("SELECT raw_response_text, parsed_json, output_hash FROM assessments WHERE run_id=1")).one()
        migrated_artifact = connection.execute(text("SELECT content, content_hash FROM document_artifacts WHERE run_id=1")).one()
        assert runs == [(1, 2, None), (2, 1, None), (3, 1, None)]
        assert prompt == ("FINAL LEGACY PROMPT", "legacy-unknown")
        assert assessment.parsed_json == legacy_json
        assert json.loads(assessment.raw_response_text) == legacy_json
        assert assessment.output_hash == hashlib.sha256(assessment.raw_response_text.encode()).hexdigest()
        assert bytes(migrated_artifact.content) == artifact
        assert migrated_artifact.content_hash == hashlib.sha256(artifact).hexdigest()
        assessments = connection.execute(text("SELECT run_id, raw_response_text, parsed_json, output_hash FROM assessments ORDER BY run_id")).all()
        assert len(assessments) == 2
        assert [row.parsed_json for row in assessments] == [legacy_json, second_json]
        for row in assessments:
            assert row.output_hash == hashlib.sha256(row.raw_response_text.encode()).hexdigest()
        rubric = connection.execute(text("SELECT generation_id, reviewer, rubric_score, comments FROM rubric_results")).one()
        assert rubric == (2, "reviewer-a", 4.5, "preserve me")

    with pytest.raises(RuntimeError, match="lossless downgrade"):
        command.downgrade(alembic_config(postgres_url), "base")
