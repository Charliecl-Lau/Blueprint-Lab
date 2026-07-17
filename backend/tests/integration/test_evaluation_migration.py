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

    command.upgrade(config, "20260717_01")

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO runs "
                "(id,experiment_id,condition_id,run_number,status,model_settings,error_type,error_message,created_at,viewer_ready_at) VALUES "
                "(2,1,1,2,'evaluation_failed','{}','evaluation_error','temporary',now(),now()),"
                "(3,1,1,3,'evaluating_quality','{}',NULL,NULL,now(),now())"
            )
        )
        connection.execute(
            text(
                "INSERT INTO assessments "
                "(id,run_id,raw_response_text,parsed_json,output_hash,schema_version,created_at) VALUES "
                "(2,2,'saved','{\"questions\": []}','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','1',now()),"
                "(3,3,'saved','{\"questions\": []}','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','1',now())"
            )
        )
        connection.execute(
            text(
                "INSERT INTO document_artifacts "
                "(id,run_id,filename,media_type,content,content_hash,created_at) VALUES "
                "(2,2,'saved.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document',"
                "decode('504b','hex'),'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',now())"
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
    run_status_constraint = _constraint_sql(inspector, "runs", "ck_runs_status")
    assert "pending" in run_status_constraint
    assert "documenting" in run_status_constraint
    assert "evaluating_quality" not in run_status_constraint
    assert "evaluation_failed" not in run_status_constraint
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
        migrated_runs = connection.execute(
            text(
                "SELECT id,status,error_type,progress_message,completed_at "
                "FROM runs WHERE id IN (2,3) ORDER BY id"
            )
        ).mappings().all()

    assert dict(legacy) == {
        "id": 7,
        "generation_id": 1,
        "reviewer": "legacy-reviewer",
        "rubric_score": 4.25,
        "comments": "preserve me",
    }
    assert migrated_runs[0]["status"] == "complete"
    assert migrated_runs[0]["error_type"] is None
    assert migrated_runs[0]["progress_message"] == "Complete"
    assert migrated_runs[0]["completed_at"] is not None
    assert migrated_runs[1]["status"] == "error"
    assert migrated_runs[1]["progress_message"] == "Assessment generation failed"
    assert migrated_runs[1]["completed_at"] is not None
