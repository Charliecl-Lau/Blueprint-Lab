"""persist Luna DOCX sessions, repairs, and verification evidence

Revision ID: 20260807_01
Revises: 20260806_01
Create Date: 2026-08-07
"""

from alembic import op
import sqlalchemy as sa

revision = "20260807_01"
down_revision = "20260806_01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "luna_docx_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("source_assessment_id", sa.Integer(), sa.ForeignKey("assessments.id"), nullable=False),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("outcome", sa.String()),
        sa.Column("container_id", sa.String()),
        sa.Column("maximum_repairs", sa.Integer(), nullable=False),
        sa.Column("repair_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_issue_codes", sa.JSON(), nullable=False),
        sa.Column("final_artifact_sha256", sa.String(64)),
        sa.Column("failure_category", sa.String()),
        sa.Column("cleanup_error_code", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", "cycle_number", name="uq_luna_docx_session_cycle"),
        sa.CheckConstraint("cycle_number >= 1", name="ck_luna_docx_session_cycle"),
        sa.CheckConstraint("maximum_repairs >= 0", name="ck_luna_docx_session_max_repairs"),
        sa.CheckConstraint("repair_count >= 0", name="ck_luna_docx_session_repairs"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_luna_docx_session_attempts"),
        sa.CheckConstraint("attempt_count = 0 OR attempt_count = repair_count + 1", name="ck_luna_docx_session_counts"),
        sa.CheckConstraint("status IN ('creating','authoring','validating','repairing','succeeded','failed')", name="ck_luna_docx_session_status"),
        sa.CheckConstraint("outcome IS NULL OR outcome IN ('succeeded','failed')", name="ck_luna_docx_session_outcome"),
    )
    op.create_table(
        "luna_docx_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("luna_docx_sessions.id"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("model_call_usage_id", sa.Integer(), sa.ForeignKey("model_call_usages.id")),
        sa.Column("provider_response_id", sa.String()),
        sa.Column("prompt_hash", sa.String(64)),
        sa.Column("input_artifact_sha256", sa.String(64)),
        sa.Column("output_artifact_sha256", sa.String(64)),
        sa.Column("issue_codes", sa.JSON(), nullable=False),
        sa.Column("validation_report", sa.JSON(), nullable=False),
        sa.Column("repair_feedback", sa.JSON(), nullable=False),
        sa.Column("provider_failure_code", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("session_id", "attempt_number", name="uq_luna_docx_attempt_number"),
        sa.UniqueConstraint("model_call_usage_id", name="uq_luna_docx_attempt_usage"),
        sa.CheckConstraint("attempt_number >= 1", name="ck_luna_docx_attempt_number"),
        sa.CheckConstraint("kind IN ('initial','repair')", name="ck_luna_docx_attempt_kind"),
        sa.CheckConstraint("status IN ('requested','generated','validating','succeeded','failed')", name="ck_luna_docx_attempt_status"),
    )


def downgrade():
    op.drop_table("luna_docx_attempts")
    op.drop_table("luna_docx_sessions")
