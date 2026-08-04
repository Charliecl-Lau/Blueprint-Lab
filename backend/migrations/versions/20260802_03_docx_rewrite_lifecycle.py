"""Add the LLM DOCX authoring lifecycle states and usage stages."""

from __future__ import annotations

from alembic import op


revision = "20260802_03"
down_revision = "20260802_02"
branch_labels = None
depends_on = None


RUN_STATUS_SQL = (
    "status IN ('pending','prompting','generating','documenting','docx_authoring',"
    "'docx_executing','docx_validating','docx_repairing','rewrite_failed',"
    "'complete','complete_with_warnings','error')"
)
USAGE_STAGE_SQL = (
    "stage IN ('actual_prompt','planning','validation','assessment','evaluation',"
    "'repair','structured_output_retry','docx_authoring','docx_repair',"
    "'docx_code_generation','docx_code_repair')"
)


def upgrade() -> None:
    op.drop_constraint("ck_runs_status", "runs", type_="check")
    op.create_check_constraint("ck_runs_status", "runs", RUN_STATUS_SQL)
    op.drop_constraint("ck_model_call_usages_stage", "model_call_usages", type_="check")
    op.create_check_constraint(
        "ck_model_call_usages_stage", "model_call_usages", USAGE_STAGE_SQL
    )


def downgrade() -> None:
    op.execute("UPDATE runs SET status='error' WHERE status IN ('docx_authoring','docx_executing','docx_validating','docx_repairing','rewrite_failed')")
    op.drop_constraint("ck_runs_status", "runs", type_="check")
    op.create_check_constraint(
        "ck_runs_status",
        "runs",
        "status IN ('pending','prompting','generating','documenting','complete','complete_with_warnings','error')",
    )
    op.execute("UPDATE model_call_usages SET stage='docx_authoring' WHERE stage='docx_code_generation'")
    op.execute("UPDATE model_call_usages SET stage='docx_repair' WHERE stage='docx_code_repair'")
    op.drop_constraint("ck_model_call_usages_stage", "model_call_usages", type_="check")
    op.create_check_constraint(
        "ck_model_call_usages_stage",
        "model_call_usages",
        "stage IN ('actual_prompt','planning','validation','assessment','evaluation','repair','structured_output_retry','docx_authoring','docx_repair')",
    )
