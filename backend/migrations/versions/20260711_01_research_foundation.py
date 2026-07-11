"""Migrate legacy generations into immutable research records."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260711_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # digest() is supplied by pgcrypto. IF NOT EXISTS is idempotent, but the
    # migration role must have permission to install an available extension.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.rename_table("generations", "runs")

    # Experiment descriptors required by the canonical model are deliberately
    # derived only from legacy evidence or marked unknown.
    op.add_column("experiments", sa.Column("name", sa.String(), nullable=True))
    op.add_column("experiments", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("experiments", sa.Column("topic_area", sa.String(), nullable=True))
    op.add_column("experiments", sa.Column("research_question", sa.Text(), nullable=True))
    op.add_column("experiments", sa.Column("status", sa.String(), nullable=True))
    op.add_column("experiments", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE experiments SET name = 'Legacy experiment ' || id, description = '', topic_area = topic, research_question = 'legacy-unknown', status = 'draft', updated_at = created_at")
    for column in ("name", "description", "topic_area", "research_question", "status", "updated_at"):
        op.alter_column("experiments", column, nullable=False)
    op.create_check_constraint("ck_experiments_status", "experiments", "status IN ('draft','active','completed','archived')")

    op.add_column("conditions", sa.Column("condition_code", sa.String(), nullable=True))
    op.add_column("conditions", sa.Column("bloom_level_enabled", sa.Boolean(), nullable=True))
    op.add_column("conditions", sa.Column("factor_configuration", sa.JSON(), nullable=True))
    op.add_column("conditions", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE conditions SET condition_code = 'legacy-' || id, bloom_level_enabled = false, factor_configuration = factor_inputs, created_at = (SELECT created_at FROM experiments WHERE experiments.id = conditions.experiment_id)")
    for column in ("condition_code", "bloom_level_enabled", "factor_configuration", "created_at"):
        op.alter_column("conditions", column, nullable=False)
    op.create_unique_constraint("uq_conditions_experiment_condition_code", "conditions", ["experiment_id", "condition_code"])

    op.add_column("runs", sa.Column("run_number", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("provider", sa.String(), nullable=True))
    op.alter_column("runs", "model_name", new_column_name="model")
    op.alter_column("runs", "model_version", new_column_name="version")
    op.add_column("runs", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("runs", sa.Column("top_p", sa.Float(), nullable=True))
    op.add_column("runs", sa.Column("seed", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("max_tokens", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("model_settings", sa.JSON(), nullable=True))
    op.add_column("runs", sa.Column("request_id", sa.String(), nullable=True))
    op.alter_column("runs", "generation_time_ms", new_column_name="duration_ms")
    op.add_column("runs", sa.Column("finish_reason", sa.String(), nullable=True))
    op.add_column("runs", sa.Column("error_type", sa.String(), nullable=True))
    op.add_column("runs", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE runs SET run_number = ranked.n, model_settings = '{}'::json, status = CASE WHEN status = 'completed' THEN 'complete' WHEN status IS NULL THEN 'pending' ELSE status END FROM (SELECT id, row_number() OVER (PARTITION BY condition_id ORDER BY created_at, id) AS n FROM runs) ranked WHERE runs.id = ranked.id")
    op.alter_column("runs", "run_number", nullable=False)
    op.alter_column("runs", "model_settings", nullable=False)

    op.rename_table("prompt_records", "prompts")
    op.alter_column("prompts", "generation_id", new_column_name="run_id")
    op.alter_column("prompts", "full_prompt", new_column_name="final_prompt")
    op.add_column("prompts", sa.Column("system_prompt", sa.Text(), nullable=True))
    op.add_column("prompts", sa.Column("template_version", sa.String(), nullable=True))
    op.add_column("prompts", sa.Column("generator_version", sa.String(), nullable=True))
    op.add_column("prompts", sa.Column("prompt_hash", sa.String(length=64), nullable=True))
    op.execute("UPDATE prompts SET system_prompt = '', template_version = 'legacy-unknown', generator_version = 'legacy-unknown'")
    op.execute("""
        DO $$ DECLARE duplicate_runs text;
        BEGIN
          SELECT string_agg(run_id::text, ', ' ORDER BY run_id) INTO duplicate_runs
          FROM (SELECT run_id FROM prompts GROUP BY run_id HAVING count(*) > 1) duplicates;
          IF duplicate_runs IS NOT NULL THEN
            RAISE EXCEPTION 'evidence-preservation error: duplicate prompt_records for run IDs: %', duplicate_runs;
          END IF;
        END $$
    """)

    op.create_table("assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False, unique=True),
        sa.Column("raw_response_text", sa.Text(), nullable=False),
        sa.Column("parsed_json", sa.JSON(), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(output_hash) = 64", name="ck_assessments_output_hash"),
    )

    op.execute("UPDATE prompts SET prompt_hash = encode(digest(convert_to(final_prompt, 'UTF8'), 'sha256'), 'hex')")
    op.execute("""
        INSERT INTO assessments (run_id, raw_response_text, parsed_json, output_hash, schema_version, created_at)
        SELECT id, generated_json::jsonb::text, generated_json,
          encode(digest(convert_to(generated_json::jsonb::text, 'UTF8'), 'sha256'), 'hex'),
          'legacy-unknown', created_at
        FROM runs WHERE generated_json IS NOT NULL
    """)

    for column in ("system_prompt", "template_version", "generator_version", "prompt_hash"):
        op.alter_column("prompts", column, nullable=False)
    op.create_unique_constraint("uq_prompts_run_id", "prompts", ["run_id"])
    op.create_check_constraint("ck_prompts_prompt_hash", "prompts", "length(prompt_hash) = 64")

    op.alter_column("document_artifacts", "generation_id", new_column_name="run_id")
    op.add_column("document_artifacts", sa.Column("content_hash", sa.String(64), nullable=True))
    op.execute("""
        DO $$ DECLARE duplicate_runs text;
        BEGIN
          SELECT string_agg(run_id::text, ', ' ORDER BY run_id) INTO duplicate_runs
          FROM (SELECT run_id FROM document_artifacts GROUP BY run_id HAVING count(*) > 1) duplicates;
          IF duplicate_runs IS NOT NULL THEN
            RAISE EXCEPTION 'evidence-preservation error: duplicate document_artifacts for run IDs: %', duplicate_runs;
          END IF;
        END $$
    """)
    op.execute("UPDATE document_artifacts SET content_hash = encode(digest(content, 'sha256'), 'hex')")
    op.alter_column("document_artifacts", "content_hash", nullable=False)
    op.create_unique_constraint("uq_document_artifacts_run_id", "document_artifacts", ["run_id"])
    op.create_check_constraint("ck_document_artifacts_content_hash", "document_artifacts", "length(content_hash) = 64")
    op.create_table("source_documents",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(), nullable=False),
        sa.Column("document_type", sa.String(), nullable=False), sa.Column("version", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False), sa.Column("media_type", sa.String(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("extracted_text", sa.Text()), sa.Column("extraction_method", sa.String()), sa.Column("description", sa.Text()),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_source_documents_content_hash"))
    op.create_table("run_source_documents",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("source_document_id", sa.Integer(), sa.ForeignKey("source_documents.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False), sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("included_text_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('course_syllabus','bridge_map','few_shot_example','rubric','reference_content','instructor_example')", name="ck_run_source_documents_role"),
        sa.CheckConstraint("length(included_text_hash) = 64", name="ck_run_source_documents_hash"),
        sa.UniqueConstraint("run_id", "role", "ordinal", name="uq_run_source_documents_run_role_ordinal"))

    op.create_unique_constraint("uq_runs_condition_run_number", "runs", ["condition_id", "run_number"])
    op.create_check_constraint("ck_runs_status", "runs", "status IN ('pending','prompting','generating','documenting','complete','error')")
    for column in ("experiment_id", "condition_id", "status", "created_at"):
        op.create_index(f"ix_runs_{column}", "runs", [column])
    op.execute("""
        DO $$ DECLARE source_count bigint; target_count bigint; invalid_count bigint;
        BEGIN
          SELECT count(*) INTO source_count FROM runs WHERE generated_json IS NOT NULL;
          SELECT count(*) INTO target_count FROM assessments a
            JOIN runs r ON r.id = a.run_id WHERE r.generated_json IS NOT NULL;
          SELECT count(*) INTO invalid_count FROM runs r
            LEFT JOIN assessments a ON a.run_id = r.id
            WHERE r.generated_json IS NOT NULL AND
              (a.run_id IS NULL OR a.raw_response_text IS NULL OR a.parsed_json IS NULL OR
               a.output_hash IS NULL OR
               a.raw_response_text <> r.generated_json::jsonb::text OR
               a.parsed_json::jsonb <> r.generated_json::jsonb OR
               a.output_hash <> encode(digest(convert_to(a.raw_response_text, 'UTF8'), 'sha256'), 'hex'));
          IF source_count <> target_count OR invalid_count <> 0 THEN
            RAISE EXCEPTION 'assessment backfill evidence validation failed: source %, target %, invalid %; generated_json retained', source_count, target_count, invalid_count;
          END IF;
        END $$
    """)
    op.drop_column("runs", "generated_json")


def downgrade() -> None:
    raise RuntimeError("lossless downgrade is impossible after immutable assessments and sources are introduced")
