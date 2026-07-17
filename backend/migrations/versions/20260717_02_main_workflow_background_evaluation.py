"""Restore the main run lifecycle and decouple background evaluation."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260717_02"
down_revision = "20260717_01"
branch_labels = None
depends_on = None


MAIN_RUN_STATUS_SQL = (
    "status IN ('pending','prompting','generating','documenting','complete','error')"
)
EVALUATION_PIPELINE_STATUS_SQL = (
    "status IN ('preparing_prompt','generating_assessment','validating_assessment',"
    "'evaluating_quality','saving_results','complete','generation_failed','evaluation_failed')"
)


def _drop_run_status_constraint() -> None:
    connection = op.get_bind()
    existing_names = set(
        connection.execute(
            sa.text(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = to_regclass('runs')
                  AND contype = 'c'
                """
            )
        )
        .scalars()
        .all()
    )
    for constraint_name in ("ck_runs_status", "runs_status_check"):
        if constraint_name in existing_names:
            op.drop_constraint(constraint_name, "runs", type_="check")
            return


def upgrade() -> None:
    _drop_run_status_constraint()
    op.execute(
        """
        UPDATE runs AS run
        SET error_type = NULL,
            error_message = NULL
        WHERE run.status = 'evaluation_failed'
          AND EXISTS (SELECT 1 FROM assessments a WHERE a.run_id = run.id)
          AND EXISTS (SELECT 1 FROM document_artifacts d WHERE d.run_id = run.id)
        """
    )
    op.execute(
        """
        UPDATE runs AS run
        SET status = CASE run.status
            WHEN 'preparing_prompt' THEN 'pending'
            WHEN 'generating_assessment' THEN 'generating'
            WHEN 'validating_assessment' THEN 'generating'
            WHEN 'generation_failed' THEN 'error'
            WHEN 'evaluating_quality' THEN CASE
                WHEN EXISTS (
                    SELECT 1 FROM assessments a WHERE a.run_id = run.id
                ) AND EXISTS (
                    SELECT 1 FROM document_artifacts d WHERE d.run_id = run.id
                ) THEN 'complete' ELSE 'error' END
            WHEN 'saving_results' THEN CASE
                WHEN EXISTS (
                    SELECT 1 FROM assessments a WHERE a.run_id = run.id
                ) AND EXISTS (
                    SELECT 1 FROM document_artifacts d WHERE d.run_id = run.id
                ) THEN 'complete' ELSE 'error' END
            WHEN 'evaluation_failed' THEN CASE
                WHEN EXISTS (
                    SELECT 1 FROM assessments a WHERE a.run_id = run.id
                ) AND EXISTS (
                    SELECT 1 FROM document_artifacts d WHERE d.run_id = run.id
                ) THEN 'complete' ELSE 'error' END
            ELSE run.status
        END
        """
    )
    op.execute(
        """
        UPDATE runs
        SET completed_at = COALESCE(completed_at, viewer_ready_at, created_at),
            progress_message = 'Complete'
        WHERE status = 'complete'
        """
    )
    op.execute(
        """
        UPDATE runs
        SET completed_at = COALESCE(completed_at, created_at),
            progress_message = 'Assessment generation failed'
        WHERE status = 'error'
        """
    )
    op.create_check_constraint("ck_runs_status", "runs", MAIN_RUN_STATUS_SQL)


def downgrade() -> None:
    _drop_run_status_constraint()
    op.execute(
        "UPDATE runs SET status = CASE status "
        "WHEN 'pending' THEN 'preparing_prompt' "
        "WHEN 'prompting' THEN 'preparing_prompt' "
        "WHEN 'generating' THEN 'generating_assessment' "
        "WHEN 'documenting' THEN 'saving_results' "
        "WHEN 'error' THEN 'generation_failed' "
        "ELSE status END"
    )
    op.create_check_constraint(
        "ck_runs_status", "runs", EVALUATION_PIPELINE_STATUS_SQL
    )
