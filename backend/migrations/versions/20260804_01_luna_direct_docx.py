"""allow direct Luna DOCX model-call usage

Revision ID: 20260804_01
Revises: 20260803_01
Create Date: 2026-08-04
"""

from alembic import op


revision = "20260804_01"
down_revision = "20260803_01"
branch_labels = None
depends_on = None


_WITH_DIRECT = (
    "stage IN ('actual_prompt','planning','validation','assessment','evaluation','repair',"
    "'structured_output_retry','docx_authoring','docx_repair','docx_code_generation',"
    "'docx_code_repair','docx_tool_design','docx_visual_review','docx_direct_generation')"
)
_WITHOUT_DIRECT = (
    "stage IN ('actual_prompt','planning','validation','assessment','evaluation','repair',"
    "'structured_output_retry','docx_authoring','docx_repair','docx_code_generation',"
    "'docx_code_repair','docx_tool_design','docx_visual_review')"
)


def upgrade():
    with op.batch_alter_table("model_call_usages") as batch:
        batch.drop_constraint("ck_model_call_usages_stage", type_="check")
        batch.create_check_constraint("ck_model_call_usages_stage", _WITH_DIRECT)


def downgrade():
    with op.batch_alter_table("model_call_usages") as batch:
        batch.drop_constraint("ck_model_call_usages_stage", type_="check")
        batch.create_check_constraint("ck_model_call_usages_stage", _WITHOUT_DIRECT)
