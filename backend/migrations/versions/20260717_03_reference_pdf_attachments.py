"""Store ordered reference PDF filenames for runs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260717_03"
down_revision = "20260717_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_reference_pdfs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.CheckConstraint(
            "ordinal >= 0 AND ordinal <= 2",
            name="ck_run_reference_pdfs_ordinal",
        ),
        sa.UniqueConstraint(
            "run_id",
            "ordinal",
            name="uq_run_reference_pdfs_run_ordinal",
        ),
    )


def downgrade() -> None:
    op.drop_table("run_reference_pdfs")
