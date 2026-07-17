from alembic import command
from sqlalchemy import create_engine, inspect, text

from backend.tests.integration.test_research_migration import alembic_config


def _constraint_sql(inspector, table_name, constraint_name):
    constraints = {
        item["name"]: item.get("sqltext", "")
        for item in inspector.get_check_constraints(table_name)
    }
    return constraints[constraint_name]


def test_evaluation_migration_adds_normalized_records_without_overwriting_legacy_rubric(postgres_url):
    engine = create_engine(postgres_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))

    config = alembic_config(postgres_url)
    command.upgrade(config, "20260716_01")

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO experiments "
                "(id,name,description,topic_area,research_question,status,course,topic,learning_objectives,"
                "assessment_type,difficulty,number_of_questions,estimated_time_minutes,created_at,updated_at,"
                "cognitive_demand,additional_instruction) VALUES "
                "(1,'Study','','MSE','Question','active','MSE302','Phase equilibria','Analyze stability',"
                "'long_answer','advanced',1,30,now(),now(),'analyze_evaluate',NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO conditions "
                "(id,experiment_id,condition_code,prompt_structure,concept_bridge_enabled,few_shot_enabled,"
                "reference_content_enabled,reasoning_guidance_enabled,bloom_level_enabled,factor_configuration,"
                "factor_inputs,condition_label,created_at) VALUES "
                "(1,1,'C100','openai',true,false,false,false,false,'{}','{}','Baseline',now())"
            )
        )
        connection.execute(
            text(
                "INSERT INTO runs "
                "(id,experiment_id,condition_id,run_number,status,model_settings,created_at) VALUES "
                "(1,1,1,1,'complete','{}',now())"
            )
        )
        connection.execute(
            text(
                "INSERT INTO rubric_results (id,generation_id,reviewer,rubric_score,comments,created_at) "
                "VALUES (7,1,'legacy-reviewer',4.25,'preserve me',now())"
            )
        )

    command.upgrade(config, "head")

    inspector = inspect(engine)
    expected_tables = {
        "assessment_questions",
        "evaluations",
        "evaluation_criteria",
        "evaluation_revisions",
        "evaluation_access_events",
    }
    assert expected_tables.issubset(set(inspector.get_table_names()))
    assert "ix_assessment_questions_content_hash" in {
        item["name"] for item in inspector.get_indexes("assessment_questions")
    }
    assert "ix_evaluations_question_type" in {
        item["name"] for item in inspector.get_indexes("evaluations")
    }
    assert "evaluating_quality" in _constraint_sql(inspector, "runs", "ck_runs_status")
    assert "evaluation_failed" in _constraint_sql(inspector, "runs", "ck_runs_status")
    assert "evaluation" in _constraint_sql(
        inspector, "model_call_usages", "ck_model_call_usages_stage"
    )

    with engine.connect() as connection:
        legacy = connection.execute(
            text(
                "SELECT id,generation_id,reviewer,rubric_score,comments "
                "FROM rubric_results WHERE id=7"
            )
        ).mappings().one()

    assert dict(legacy) == {
        "id": 7,
        "generation_id": 1,
        "reviewer": "legacy-reviewer",
        "rubric_score": 4.25,
        "comments": "preserve me",
    }
