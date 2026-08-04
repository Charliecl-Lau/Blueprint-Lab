"""Persist bounded DOCX authoring attempts and their evidence."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260802_02"
down_revision = "20260802_01"
branch_labels = None
depends_on = None


MODEL_CALL_STAGE_SQL = (
    "stage IN ('actual_prompt','planning','validation','assessment','evaluation',"
    "'repair','structured_output_retry','docx_authoring','docx_repair')"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_model_call_usages_stage", "model_call_usages", type_="check"
    )
    op.create_check_constraint(
        "ck_model_call_usages_stage", "model_call_usages", MODEL_CALL_STAGE_SQL
    )

    op.create_table(
        "docx_authoring_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("source_assessment_id", sa.Integer(), nullable=False),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=True),
        sa.Column("provider_request_id", sa.String(), nullable=True),
        sa.Column(
            "model_call_usage_id",
            sa.Integer(),
            sa.ForeignKey("model_call_usages.id"),
            nullable=True,
        ),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("grounding_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("program_text", sa.Text(), nullable=True),
        sa.Column("envelope", sa.JSON(), nullable=False),
        sa.Column("sandbox_image_digest", sa.String(64), nullable=True),
        sa.Column("execution_report", sa.JSON(), nullable=False),
        sa.Column("validation_report", sa.JSON(), nullable=False),
        sa.Column("failure_category", sa.String(), nullable=True),
        sa.Column("repairable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "run_id",
            "cycle_number",
            "attempt_number",
            name="uq_docx_authoring_attempt_cycle",
        ),
        sa.UniqueConstraint(
            "model_call_usage_id", name="uq_docx_authoring_attempt_usage"
        ),
        sa.CheckConstraint(
            "cycle_number >= 1", name="ck_docx_authoring_cycle_positive"
        ),
        sa.CheckConstraint(
            "attempt_number IN (1, 2)", name="ck_docx_authoring_attempt_bounded"
        ),
        sa.CheckConstraint(
            "status IN ('requested','generated','executing','validating',"
            "'succeeded','failed')",
            name="ck_docx_authoring_status",
        ),
        sa.CheckConstraint(
            "length(prompt_hash) = 64", name="ck_docx_authoring_prompt_hash"
        ),
        sa.CheckConstraint(
            "length(grounding_hash) = 64",
            name="ck_docx_authoring_grounding_hash",
        ),
        sa.CheckConstraint(
            "sandbox_image_digest IS NULL OR length(sandbox_image_digest) = 64",
            name="ck_docx_authoring_sandbox_digest",
        ),
        sa.CheckConstraint(
            "idempotency_key IS NULL OR attempt_number = 1",
            name="ck_docx_authoring_idempotency_initial_only",
        ),
        sa.CheckConstraint(
            "repairable = false OR failure_category IS NULL OR "
            "failure_category NOT IN ('hostile_code','security_violation')",
            name="ck_docx_authoring_security_not_repairable",
        ),
        sa.ForeignKeyConstraint(
            ["source_assessment_id", "run_id"],
            ["assessments.id", "assessments.run_id"],
            name="fk_docx_authoring_source_same_run",
        ),
    )
    op.create_index(
        "uq_docx_authoring_run_idempotency",
        "docx_authoring_attempts",
        ["run_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_docx_authoring_run_idempotency",
        table_name="docx_authoring_attempts",
    )
    op.drop_table("docx_authoring_attempts")
    op.drop_constraint(
        "ck_model_call_usages_stage", "model_call_usages", type_="check"
    )
    op.create_check_constraint(
        "ck_model_call_usages_stage",
        "model_call_usages",
        "stage IN ('actual_prompt','planning','validation','assessment','evaluation',"
        "'repair','structured_output_retry')",
    )
