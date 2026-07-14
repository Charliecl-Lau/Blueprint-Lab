"""Add per-call model usage and legacy-safe run aggregates."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260714_01"
down_revision = "20260712_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("experiments", sa.Column("idempotency_key", sa.String(64), nullable=True))
    op.create_index(
        "ix_experiments_idempotency_key",
        "experiments",
        ["idempotency_key"],
        unique=True,
    )

    for column_name in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "model_call_count",
    ):
        op.add_column("runs", sa.Column(column_name, sa.Integer(), nullable=True))
        op.create_check_constraint(
            f"ck_runs_{column_name}_nonnegative",
            "runs",
            f"{column_name} IS NULL OR {column_name} >= 0",
        )

    op.create_table(
        "model_call_usages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("provider_response_id", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_content_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("extra_token_counts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "stage IN ('actual_prompt','planning','validation','assessment','repair','structured_output_retry')",
            name="ck_model_call_usages_stage",
        ),
        sa.CheckConstraint(
            "status IN ('response','response_without_usage','failed')",
            name="ck_model_call_usages_status",
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_model_call_usages_attempt"),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_model_call_usages_input_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_model_call_usages_output_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="ck_model_call_usages_total_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "cached_content_tokens IS NULL OR cached_content_tokens >= 0",
            name="ck_model_call_usages_cached_content_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "reasoning_tokens IS NULL OR reasoning_tokens >= 0",
            name="ck_model_call_usages_reasoning_tokens_nonnegative",
        ),
        sa.UniqueConstraint("call_id", name="uq_model_call_usages_call_id"),
    )
    op.create_index(
        "ix_model_call_usages_run_stage",
        "model_call_usages",
        ["run_id", "stage"],
    )
    op.create_index(
        "uq_model_call_usages_provider_response_id",
        "model_call_usages",
        ["provider_response_id"],
        unique=True,
        postgresql_where=sa.text("provider_response_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_model_call_usages_provider_response_id",
        table_name="model_call_usages",
    )
    op.drop_index("ix_model_call_usages_run_stage", table_name="model_call_usages")
    op.drop_table("model_call_usages")

    for column_name in reversed(
        ("input_tokens", "output_tokens", "total_tokens", "model_call_count")
    ):
        op.drop_constraint(
            f"ck_runs_{column_name}_nonnegative", "runs", type_="check"
        )
        op.drop_column("runs", column_name)

    op.drop_index("ix_experiments_idempotency_key", table_name="experiments")
    op.drop_column("experiments", "idempotency_key")
