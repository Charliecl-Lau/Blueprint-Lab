"""add replayable agentic DOCX tool evidence

Revision ID: 20260803_01
Revises: 20260802_03
Create Date: 2026-08-03
"""

from alembic import op
import sqlalchemy as sa

revision = "20260803_01"
down_revision = "20260802_03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "docx_tool_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("source_assessment_id", sa.Integer(), nullable=False),
        sa.Column("cycle_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False), sa.Column("model", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("content_catalog_hash", sa.String(64), nullable=False),
        sa.Column("design_contract_hash", sa.String(64), nullable=False),
        sa.Column("workspace_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("initial_workspace_hash", sa.String(64)), sa.Column("final_workspace_hash", sa.String(64)),
        sa.Column("maximum_revisions", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("final_decision", sa.String()), sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["source_assessment_id", "run_id"], ["assessments.id", "assessments.run_id"], name="fk_docx_tool_session_source_same_run"),
        sa.UniqueConstraint("run_id", "cycle_number", name="uq_docx_tool_sessions_run_cycle"),
        sa.UniqueConstraint("idempotency_key", name="uq_docx_tool_sessions_idempotency"),
        sa.CheckConstraint("cycle_number >= 1", name="ck_docx_tool_session_cycle"),
        sa.CheckConstraint("workspace_revision >= 0", name="ck_docx_tool_session_revision"),
        sa.CheckConstraint("maximum_revisions >= 0 AND maximum_revisions <= 10", name="ck_docx_tool_session_max_revisions"),
        sa.CheckConstraint("status IN ('pending','designing','executing','validating','reviewing','succeeded','failed')", name="ck_docx_tool_session_status"),
        sa.CheckConstraint("final_decision IS NULL OR final_decision IN ('approve','reject','budget_exhausted','machine_failed')", name="ck_docx_tool_session_decision"),
        sa.CheckConstraint("length(content_catalog_hash) = 64", name="ck_docx_tool_session_catalog_hash"),
        sa.CheckConstraint("length(design_contract_hash) = 64", name="ck_docx_tool_session_contract_hash"),
    )
    op.create_table(
        "docx_tool_iterations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("session_id", sa.Integer(), sa.ForeignKey("docx_tool_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("iteration_number", sa.Integer(), nullable=False), sa.Column("kind", sa.String(), nullable=False),
        sa.Column("model_call_usage_id", sa.Integer(), sa.ForeignKey("model_call_usages.id")),
        sa.Column("input_workspace_hash", sa.String(64), nullable=False), sa.Column("output_workspace_hash", sa.String(64)),
        sa.Column("draft_docx_hash", sa.String(64)), sa.Column("draft_pdf_hash", sa.String(64)),
        sa.Column("page_image_metadata", sa.JSON(), nullable=False), sa.Column("validator_report", sa.JSON(), nullable=False),
        sa.Column("review_decision", sa.String()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("session_id", "iteration_number", name="uq_docx_tool_iteration_number"),
        sa.UniqueConstraint("model_call_usage_id", name="uq_docx_tool_iteration_usage"),
        sa.CheckConstraint("iteration_number >= 0 AND iteration_number <= 10", name="ck_docx_tool_iteration_bounded"),
        sa.CheckConstraint("kind IN ('design','visual_revision')", name="ck_docx_tool_iteration_kind"),
        sa.CheckConstraint("review_decision IS NULL OR review_decision IN ('approve','revise','reject')", name="ck_docx_tool_iteration_review"),
    )
    op.create_table(
        "docx_tool_actions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("session_id", sa.Integer(), sa.ForeignKey("docx_tool_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("iteration_id", sa.Integer(), sa.ForeignKey("docx_tool_iterations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False), sa.Column("operation_id", sa.String(128), nullable=False), sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("validated_arguments", sa.JSON(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("safe_error_code", sa.String(64)),
        sa.Column("before_workspace_hash", sa.String(64), nullable=False), sa.Column("after_workspace_hash", sa.String(64)), sa.Column("duration_ms", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "operation_id", name="uq_docx_tool_action_operation"),
        sa.UniqueConstraint("iteration_id", "sequence_number", name="uq_docx_tool_action_sequence"),
        sa.CheckConstraint("sequence_number >= 0", name="ck_docx_tool_action_sequence"),
        sa.CheckConstraint("status IN ('accepted','succeeded','failed')", name="ck_docx_tool_action_status"),
        sa.CheckConstraint("duration_ms >= 0", name="ck_docx_tool_action_duration"),
    )
    op.create_index("ix_docx_tool_actions_session", "docx_tool_actions", ["session_id"])
    with op.batch_alter_table("model_call_usages") as batch:
        batch.drop_constraint("ck_model_call_usages_stage", type_="check")
        batch.create_check_constraint("ck_model_call_usages_stage", "stage IN ('actual_prompt','planning','validation','assessment','evaluation','repair','structured_output_retry','docx_authoring','docx_repair','docx_code_generation','docx_code_repair','docx_tool_design','docx_visual_review')")


def downgrade():
    with op.batch_alter_table("model_call_usages") as batch:
        batch.drop_constraint("ck_model_call_usages_stage", type_="check")
        batch.create_check_constraint("ck_model_call_usages_stage", "stage IN ('actual_prompt','planning','validation','assessment','evaluation','repair','structured_output_retry','docx_authoring','docx_repair','docx_code_generation','docx_code_repair')")
    op.drop_index("ix_docx_tool_actions_session", table_name="docx_tool_actions")
    op.drop_table("docx_tool_actions")
    op.drop_table("docx_tool_iterations")
    op.drop_table("docx_tool_sessions")
