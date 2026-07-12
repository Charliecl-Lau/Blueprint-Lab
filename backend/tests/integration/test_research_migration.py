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
LEGACY_DDL = """
CREATE TABLE experiments (id SERIAL PRIMARY KEY, course VARCHAR NOT NULL, topic VARCHAR NOT NULL,
 learning_objectives VARCHAR NOT NULL, assessment_type VARCHAR NOT NULL, difficulty VARCHAR NOT NULL,
 number_of_questions INTEGER NOT NULL, estimated_time_minutes INTEGER NOT NULL, created_at TIMESTAMP NOT NULL);
CREATE TABLE conditions (id SERIAL PRIMARY KEY, experiment_id INTEGER NOT NULL REFERENCES experiments(id),
 prompt_structure VARCHAR NOT NULL, concept_bridge_enabled BOOLEAN NOT NULL, few_shot_enabled BOOLEAN NOT NULL,
 reference_content_enabled BOOLEAN NOT NULL, reasoning_guidance_enabled BOOLEAN NOT NULL, factor_inputs JSON NOT NULL, condition_label VARCHAR NOT NULL);
CREATE TABLE generations (id SERIAL PRIMARY KEY, experiment_id INTEGER NOT NULL REFERENCES experiments(id), condition_id INTEGER NOT NULL REFERENCES conditions(id),
 status VARCHAR, model_name VARCHAR, model_version VARCHAR, generation_time_ms INTEGER, generated_json JSON, created_at TIMESTAMP NOT NULL, completed_at TIMESTAMP);
CREATE TABLE prompt_records (id SERIAL PRIMARY KEY, generation_id INTEGER NOT NULL REFERENCES generations(id), prompt_structure VARCHAR NOT NULL, full_prompt VARCHAR NOT NULL, created_at TIMESTAMP NOT NULL);
CREATE TABLE document_artifacts (id SERIAL PRIMARY KEY, generation_id INTEGER NOT NULL REFERENCES generations(id), filename VARCHAR NOT NULL, media_type VARCHAR NOT NULL, content BYTEA NOT NULL, created_at TIMESTAMP NOT NULL);
CREATE TABLE rubric_results (id SERIAL PRIMARY KEY, generation_id INTEGER NOT NULL REFERENCES generations(id), reviewer VARCHAR, rubric_score FLOAT, comments VARCHAR, created_at TIMESTAMP NOT NULL);
"""


def alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    return config


def test_revision_refuses_offline_sql_with_actionable_message():
    env = os.environ | {"DATABASE_URL": "postgresql+psycopg://unused:unused@localhost/unused"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "offline SQL migration is refused" in result.stderr
    assert "python -m alembic upgrade head" in result.stderr
    assert "ALTER TABLE generations RENAME TO runs" not in result.stdout


def test_upgrade_preserves_exact_legacy_evidence(postgres_url):
    engine = create_engine(postgres_url)
    legacy_json = {
        "β": "unicode", "a": {"exp": 1e-7, "decimal": 1.25}, "A": "upper",
        "!": "punct", "é": "accent", "esc": "backslash\\ newline\n tab\t control\x01",
        "array": [True, None, {"z": 2, "a": 1}],
    }
    expected_raw = '{"!":"punct","A":"upper","a":{"decimal":1.25,"exp":1e-07},"array":[true,null,{"a":1,"z":2}],"esc":"backslash\\\\ newline\\n tab\\t control\\u0001","é":"accent","β":"unicode"}'
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

    command.upgrade(alembic_config(postgres_url), "20260711_01")
    with engine.connect() as connection:
        legacy_prompt_text = connection.scalar(text("SELECT final_prompt FROM prompts WHERE run_id=1"))
    command.upgrade(alembic_config(postgres_url), "head")
    with engine.connect() as connection:
        runs = connection.execute(text("SELECT id, run_number, seed FROM runs ORDER BY id")).all()
        prompt = connection.execute(text("""
            SELECT actual_prompt, actual_prompt_generator_version, actual_prompt_hash,
                   generation_envelope_hash
            FROM prompts WHERE run_id=1
        """)).one()
        assessment = connection.execute(text("SELECT raw_response_text, parsed_json, output_hash FROM assessments WHERE run_id=1")).one()
        migrated_artifact = connection.execute(text("SELECT content, content_hash FROM document_artifacts WHERE run_id=1")).one()
        assert runs == [(1, 2, None), (2, 1, None), (3, 1, None)]
        assert prompt.actual_prompt == legacy_prompt_text == "FINAL LEGACY PROMPT"
        assert prompt.actual_prompt_generator_version == "legacy-unknown"
        assert len(prompt.actual_prompt_hash) == 64
        assert len(prompt.generation_envelope_hash) == 64
        assert assessment.parsed_json == legacy_json
        assert assessment.raw_response_text == expected_raw
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


@pytest.mark.parametrize(
    ("table", "insert_sql", "error"),
    [
        ("prompt_records", "INSERT INTO prompt_records (generation_id,prompt_structure,full_prompt,created_at) VALUES (1,'s','p1',now()),(1,'s','p2',now())", "duplicate prompt_records for run IDs: 1"),
        ("document_artifacts", "INSERT INTO document_artifacts (generation_id,filename,media_type,content,created_at) VALUES (1,'a','x',decode('01','hex'),now()),(1,'b','x',decode('02','hex'),now())", "duplicate document_artifacts for run IDs: 1"),
    ],
)
def test_duplicate_legacy_evidence_aborts_and_rolls_back(postgres_url, table, insert_sql, error):
    engine = create_engine(postgres_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        connection.execute(text(LEGACY_DDL))
        connection.execute(text("INSERT INTO experiments VALUES (1,'C','T','L','quiz','m',1,30,now())"))
        connection.execute(text("INSERT INTO conditions VALUES (1,1,'s',false,false,false,false,'{}','c')"))
        connection.execute(text("INSERT INTO generations VALUES (1,1,1,'complete',NULL,NULL,NULL,'{\"x\":1}',now(),now())"))
        connection.execute(text(insert_sql))
    with pytest.raises(Exception, match=error):
        command.upgrade(alembic_config(postgres_url), "head")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.generations')")) == "generations"
        assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 2
        assert connection.scalar(text("SELECT generated_json IS NOT NULL FROM generations WHERE id=1")) is True
