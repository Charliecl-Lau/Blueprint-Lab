import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


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


def test_upgrade_preserves_exact_legacy_evidence(postgres_url):
    engine = create_engine(postgres_url)
    legacy_json = {"questions": [{"text": "What is stress?", "points": 4}]}
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
        connection.execute(text("INSERT INTO generations VALUES (1,1,1,'complete','gemma','v1',123,:payload,now(),now())"), {"payload": json.dumps(legacy_json)})
        connection.execute(text("INSERT INTO prompt_records VALUES (1,1,'structured','FINAL LEGACY PROMPT',now())"))
        connection.execute(text("INSERT INTO document_artifacts VALUES (1,1,'quiz.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document',:content,now())"), {"content": artifact})

    command.upgrade(alembic_config(postgres_url), "head")
    with engine.connect() as connection:
        run = connection.execute(text("SELECT run_number, seed FROM runs WHERE id=1")).one()
        prompt = connection.execute(text("SELECT final_prompt, generator_version FROM prompts WHERE run_id=1")).one()
        assessment = connection.execute(text("SELECT raw_response_text, parsed_json, output_hash FROM assessments WHERE run_id=1")).one()
        migrated_artifact = connection.execute(text("SELECT content, content_hash FROM document_artifacts WHERE run_id=1")).one()
        assert run == (1, None)
        assert prompt == ("FINAL LEGACY PROMPT", "legacy-unknown")
        assert assessment.parsed_json == legacy_json
        assert assessment.raw_response_text == json.dumps(legacy_json, sort_keys=True, separators=(",", ":"))
        assert assessment.output_hash == hashlib.sha256(assessment.raw_response_text.encode()).hexdigest()
        assert bytes(migrated_artifact.content) == artifact
        assert migrated_artifact.content_hash == hashlib.sha256(artifact).hexdigest()

    with pytest.raises(RuntimeError, match="lossless downgrade"):
        command.downgrade(alembic_config(postgres_url), "base")
