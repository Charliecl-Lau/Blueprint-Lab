"""Persist assessment recovery and warning acceptance state."""

from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa
from alembic import context, op


revision = "20260727_01"
down_revision = "20260717_03"
branch_labels = None
depends_on = None


RUN_STATUS_SQL = (
    "status IN ('pending','prompting','generating','documenting','complete',"
    "'complete_with_warnings','error')"
)


def _drop_run_status_constraint() -> None:
    connection = op.get_bind()
    names = set(
        connection.execute(
            sa.text(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = to_regclass('runs') AND contype = 'c'
                """
            )
        ).scalars()
    )
    for name in ("ck_runs_status", "runs_status_check"):
        if name in names:
            op.drop_constraint(name, "runs", type_="check")
            return


def _canonical_json_hash(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError(
            "assessment recovery migration requires online Python JSON hashing"
        )
    _drop_run_status_constraint()
    op.create_check_constraint("ck_runs_status", "runs", RUN_STATUS_SQL)

    op.add_column(
        "assessments",
        sa.Column("validation_status", sa.String(), nullable=True),
    )
    op.add_column(
        "assessments",
        sa.Column("validation_issues", sa.JSON(), nullable=True),
    )
    op.add_column(
        "assessments",
        sa.Column("recovery_actions", sa.JSON(), nullable=True),
    )
    op.add_column(
        "assessments",
        sa.Column("parsed_json_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "assessments",
        sa.Column("defects_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "assessments",
        sa.Column("defects_accepted_by", sa.String(), nullable=True),
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, parsed_json FROM assessments")
    ).mappings()
    for row in rows:
        parsed = row["parsed_json"]
        connection.execute(
            sa.text(
                """
                UPDATE assessments
                SET validation_status=:status,
                    validation_issues=:issues,
                    recovery_actions=:actions,
                    parsed_json_hash=:parsed_hash
                WHERE id=:id
                """
            ).bindparams(
                sa.bindparam("issues", type_=sa.JSON()),
                sa.bindparam("actions", type_=sa.JSON()),
            ),
            {
                "id": row["id"],
                "status": "valid" if parsed is not None else "invalid",
                "issues": [],
                "actions": [],
                "parsed_hash": _canonical_json_hash(parsed) if parsed is not None else None,
            },
        )

    for column in ("validation_status", "validation_issues", "recovery_actions"):
        op.alter_column("assessments", column, nullable=False)
    op.create_check_constraint(
        "ck_assessments_validation_status",
        "assessments",
        "validation_status IN ('valid','warning','invalid')",
    )
    op.create_check_constraint(
        "ck_assessments_parsed_json_hash",
        "assessments",
        "parsed_json_hash IS NULL OR length(parsed_json_hash) = 64",
    )
    op.create_check_constraint(
        "ck_assessments_warning_acceptance",
        "assessments",
        "defects_accepted_at IS NULL OR validation_status = 'warning'",
    )


def downgrade() -> None:
    _drop_run_status_constraint()
    op.execute(
        "UPDATE runs SET status='error' WHERE status='complete_with_warnings'"
    )
    op.create_check_constraint(
        "ck_runs_status",
        "runs",
        "status IN ('pending','prompting','generating','documenting','complete','error')",
    )
    op.drop_constraint("ck_assessments_warning_acceptance", "assessments", type_="check")
    op.drop_constraint("ck_assessments_parsed_json_hash", "assessments", type_="check")
    op.drop_constraint("ck_assessments_validation_status", "assessments", type_="check")
    op.drop_column("assessments", "defects_accepted_by")
    op.drop_column("assessments", "defects_accepted_at")
    op.drop_column("assessments", "parsed_json_hash")
    op.drop_column("assessments", "recovery_actions")
    op.drop_column("assessments", "validation_issues")
    op.drop_column("assessments", "validation_status")
