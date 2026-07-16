"""Add cognitive demand and optional assessment instructions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260716_01"
down_revision = "20260714_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "experiments",
        sa.Column(
            "cognitive_demand",
            sa.String(),
            nullable=False,
            server_default="remember_understand",
        ),
    )
    op.add_column(
        "experiments",
        sa.Column("additional_instruction", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("experiments", "additional_instruction")
    op.drop_column("experiments", "cognitive_demand")
