"""persist question-scoped assessment repair evidence

Revision ID: 20260806_01
Revises: 20260804_01
Create Date: 2026-08-06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260806_01"
down_revision = "20260804_01"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_assessments_kind", "assessments", type_="check")
    op.create_check_constraint(
        "ck_assessments_kind",
        "assessments",
        "kind IN ('original_generation','localized_repair','full_rewrite')",
    )
    op.create_table(
        "assessment_repair_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("assessment_id", sa.Integer(), sa.ForeignKey("assessments.id")),
        sa.Column(
            "model_call_usage_id",
            sa.Integer(),
            sa.ForeignKey("model_call_usages.id"),
        ),
        sa.Column("question_ordinal", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("repair_type", sa.String(), nullable=False, server_default="structural"),
        sa.Column("error_type", sa.String()),
        sa.Column("validator_code", sa.String()),
        sa.Column("validator_message", sa.Text()),
        sa.Column("target_path", sa.String()),
        sa.Column("target_section", sa.String()),
        sa.Column("question_id", sa.String()),
        sa.Column("solution_id", sa.String()),
        sa.Column("equation_id", sa.String()),
        sa.Column("repair_scope", sa.String()),
        sa.Column("before_content", sa.JSON()),
        sa.Column("after_content", sa.JSON()),
        sa.Column("before_hash", sa.String(64)),
        sa.Column("after_hash", sa.String(64)),
        sa.Column("model", sa.String()),
        sa.Column("model_call_id", sa.String()),
        sa.Column("prompt_version", sa.String()),
        sa.Column("token_usage", sa.JSON()),
        sa.Column("success", sa.Boolean()),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "question_ordinal >= 0", name="ck_assessment_repair_question"
        ),
        sa.CheckConstraint(
            "attempt_number >= 1",
            name="ck_assessment_repair_attempt_number",
        ),
        sa.CheckConstraint(
            "status IN ('pending','response','invalid','merged')",
            name="ck_assessment_repair_status",
        ),
    )
    op.create_index(
        "ix_assessment_repair_run_attempt",
        "assessment_repair_attempts",
        ["run_id", "attempt_number"],
    )
    op.create_index(
        "ix_assessment_repair_validator_code",
        "assessment_repair_attempts",
        ["validator_code"],
    )
    op.create_index(
        "ix_assessment_repair_target_section",
        "assessment_repair_attempts",
        ["target_section"],
    )
    op.create_index(
        "ix_assessment_repair_success",
        "assessment_repair_attempts",
        ["success"],
    )


def downgrade():
    op.drop_table("assessment_repair_attempts")
    op.drop_constraint("ck_assessments_kind", "assessments", type_="check")
    op.create_check_constraint(
        "ck_assessments_kind",
        "assessments",
        "kind IN ('original_generation','full_rewrite')",
    )
