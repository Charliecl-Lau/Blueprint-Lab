"""Version assessments and make canonical selection explicit."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op


revision = "20260802_01"
down_revision = "20260727_02"
branch_labels = None
depends_on = None


def _drop_single_column_unique(table: str, column: str) -> None:
    if context.is_offline_mode():
        known_names = {
            ("assessments", "run_id"): "assessments_run_id_key",
            ("document_artifacts", "run_id"): "uq_document_artifacts_run_id",
        }
        op.drop_constraint(known_names[(table, column)], table, type_="unique")
        return
    connection = op.get_bind()
    for constraint in sa.inspect(connection).get_unique_constraints(table):
        if constraint.get("column_names") == [column]:
            op.drop_constraint(constraint["name"], table, type_="unique")
            return


def upgrade() -> None:
    connection = op.get_bind()

    op.add_column("assessments", sa.Column("version", sa.Integer(), nullable=True))
    op.add_column("assessments", sa.Column("kind", sa.String(), nullable=True))
    op.add_column(
        "assessments", sa.Column("source_assessment_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "assessments",
        sa.Column("canonicalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    connection.execute(
        sa.text(
            "UPDATE assessments SET version=1, kind='original_generation'"
        )
    )
    op.alter_column("assessments", "version", nullable=False)
    op.alter_column("assessments", "kind", nullable=False)
    _drop_single_column_unique("assessments", "run_id")
    op.create_unique_constraint(
        "uq_assessments_run_version", "assessments", ["run_id", "version"]
    )
    op.create_unique_constraint(
        "uq_assessments_id_run", "assessments", ["id", "run_id"]
    )
    op.create_check_constraint(
        "ck_assessments_version_positive", "assessments", "version >= 1"
    )
    op.create_check_constraint(
        "ck_assessments_kind",
        "assessments",
        "kind IN ('original_generation','full_rewrite')",
    )
    op.create_foreign_key(
        "fk_assessments_source_assessment",
        "assessments",
        "assessments",
        ["source_assessment_id"],
        ["id"],
    )

    op.add_column(
        "runs", sa.Column("canonical_assessment_id", sa.Integer(), nullable=True)
    )
    connection.execute(
        sa.text(
            """
            UPDATE runs AS run
            SET canonical_assessment_id=assessment.id
            FROM assessments AS assessment
            WHERE assessment.run_id=run.id AND assessment.version=1
            """
        )
    )
    op.create_foreign_key(
        "fk_runs_canonical_assessment_same_run",
        "runs",
        "assessments",
        ["canonical_assessment_id", "id"],
        ["id", "run_id"],
        deferrable=True,
        initially="DEFERRED",
    )

    op.add_column(
        "document_artifacts", sa.Column("assessment_id", sa.Integer(), nullable=True)
    )
    connection.execute(
        sa.text(
            """
            UPDATE document_artifacts AS artifact
            SET assessment_id=assessment.id
            FROM assessments AS assessment
            WHERE assessment.run_id=artifact.run_id AND assessment.version=1
            """
        )
    )
    if not context.is_offline_mode():
        orphan_count = connection.scalar(
            sa.text(
                "SELECT count(*) FROM document_artifacts WHERE assessment_id IS NULL"
            )
        )
        if orphan_count:
            raise RuntimeError(
                f"cannot version {orphan_count} document artifacts without assessments"
            )
    op.alter_column("document_artifacts", "assessment_id", nullable=False)
    _drop_single_column_unique("document_artifacts", "run_id")
    op.create_unique_constraint(
        "uq_document_artifacts_assessment",
        "document_artifacts",
        ["assessment_id"],
    )
    op.create_foreign_key(
        "fk_document_artifacts_assessment_same_run",
        "document_artifacts",
        "assessments",
        ["assessment_id", "run_id"],
        ["id", "run_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    if (
        not context.is_offline_mode()
        and connection.scalar(
            sa.text("SELECT count(*) FROM assessments WHERE version <> 1")
        )
    ):
        raise RuntimeError("cannot losslessly downgrade databases with rewrite versions")

    op.drop_constraint(
        "fk_document_artifacts_assessment_same_run",
        "document_artifacts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_document_artifacts_assessment", "document_artifacts", type_="unique"
    )
    op.create_unique_constraint(
        "uq_document_artifacts_run_id", "document_artifacts", ["run_id"]
    )
    op.drop_column("document_artifacts", "assessment_id")
    op.drop_constraint(
        "fk_runs_canonical_assessment_same_run", "runs", type_="foreignkey"
    )
    op.drop_column("runs", "canonical_assessment_id")
    op.drop_constraint(
        "fk_assessments_source_assessment", "assessments", type_="foreignkey"
    )
    op.drop_constraint("ck_assessments_kind", "assessments", type_="check")
    op.drop_constraint(
        "ck_assessments_version_positive", "assessments", type_="check"
    )
    op.drop_constraint("uq_assessments_id_run", "assessments", type_="unique")
    op.drop_constraint("uq_assessments_run_version", "assessments", type_="unique")
    op.create_unique_constraint("uq_assessments_run_id", "assessments", ["run_id"])
    op.drop_column("assessments", "canonicalized_at")
    op.drop_column("assessments", "source_assessment_id")
    op.drop_column("assessments", "kind")
    op.drop_column("assessments", "version")
