"""Add normalized assessment evaluation records and pipeline progress."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260717_01"
down_revision = "20260716_01"
branch_labels = None
depends_on = None


NEW_RUN_STATUS_SQL = (
    "status IN ('preparing_prompt','generating_assessment','validating_assessment',"
    "'evaluating_quality','saving_results','complete','generation_failed','evaluation_failed')"
)
LEGACY_RUN_STATUS_SQL = (
    "status IN ('pending','prompting','generating','documenting','complete','error')"
)
USAGE_STAGE_SQL = (
    "stage IN ('actual_prompt','planning','validation','assessment','evaluation','repair',"
    "'structured_output_retry')"
)
LEGACY_USAGE_STAGE_SQL = (
    "stage IN ('actual_prompt','planning','validation','assessment','repair','structured_output_retry')"
)
CRITERION_KEY_SQL = (
    "criterion_key IN ('technical_correctness','course_alignment','blooms_alignment',"
    "'clarity_solution','materials_context')"
)


def _drop_check_constraint_if_present(
    table_name: str, constraint_names: tuple[str, ...]
) -> None:
    connection = op.get_bind()
    existing_names = set(
        connection.execute(
            sa.text(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = to_regclass(:table_name)
                  AND contype = 'c'
                """
            ),
            {"table_name": table_name},
        )
        .scalars()
        .all()
    )
    for constraint_name in constraint_names:
        if constraint_name in existing_names:
            op.drop_constraint(constraint_name, table_name, type_="check")
            return


def upgrade() -> None:
    _drop_check_constraint_if_present(
        "runs", ("ck_runs_status", "runs_status_check")
    )
    op.execute(
        "UPDATE runs SET status = CASE status "
        "WHEN 'pending' THEN 'preparing_prompt' "
        "WHEN 'prompting' THEN 'preparing_prompt' "
        "WHEN 'generating' THEN 'generating_assessment' "
        "WHEN 'documenting' THEN 'saving_results' "
        "WHEN 'error' THEN 'generation_failed' "
        "ELSE status END"
    )
    op.create_check_constraint("ck_runs_status", "runs", NEW_RUN_STATUS_SQL)
    op.add_column(
        "runs", sa.Column("viewer_ready_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("runs", sa.Column("progress_message", sa.Text(), nullable=True))

    _drop_check_constraint_if_present(
        "model_call_usages",
        ("ck_model_call_usages_stage", "model_call_usages_stage_check"),
    )
    op.create_check_constraint(
        "ck_model_call_usages_stage", "model_call_usages", USAGE_STAGE_SQL
    )

    op.create_table(
        "assessment_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "assessment_id",
            sa.Integer(),
            sa.ForeignKey("assessments.id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("assessment_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ordinal >= 0", name="ck_assessment_questions_ordinal"
        ),
        sa.CheckConstraint(
            "assessment_version >= 1", name="ck_assessment_questions_version"
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_assessment_questions_content_hash",
        ),
        sa.UniqueConstraint(
            "assessment_id",
            "ordinal",
            name="uq_assessment_questions_ordinal",
        ),
    )
    op.create_index(
        "ix_assessment_questions_content_hash",
        "assessment_questions",
        ["assessment_id", "content_hash"],
    )

    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "experiment_id",
            sa.Integer(),
            sa.ForeignKey("experiments.id"),
            nullable=False,
        ),
        sa.Column(
            "condition_id",
            sa.Integer(),
            sa.ForeignKey("conditions.id"),
            nullable=False,
        ),
        sa.Column(
            "run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False
        ),
        sa.Column(
            "assessment_id",
            sa.Integer(),
            sa.ForeignKey("assessments.id"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Integer(),
            sa.ForeignKey("assessment_questions.id"),
            nullable=False,
        ),
        sa.Column("assessment_version", sa.Integer(), nullable=False),
        sa.Column("assessment_content_hash", sa.String(64), nullable=False),
        sa.Column("evaluation_type", sa.String(), nullable=False),
        sa.Column("evaluator_identity", sa.String(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("evaluation_model", sa.String(), nullable=True),
        sa.Column("evaluation_model_version", sa.String(), nullable=True),
        sa.Column("rubric_version", sa.String(), nullable=False),
        sa.Column("rubric_snapshot", sa.JSON(), nullable=False),
        sa.Column("prompt_template_id", sa.String(), nullable=True),
        sa.Column("actual_prompt_id", sa.String(), nullable=True),
        sa.Column("output_id", sa.String(), nullable=True),
        sa.Column("generation_model", sa.String(), nullable=True),
        sa.Column("generation_model_version", sa.String(), nullable=True),
        sa.Column("prompt_design_factors", sa.JSON(), nullable=False),
        sa.Column("weighted_score", sa.Float(), nullable=True),
        sa.Column("critical_gate", sa.String(), nullable=True),
        sa.Column("overall_decision", sa.String(), nullable=True),
        sa.Column("instructor_readiness", sa.String(), nullable=True),
        sa.Column("highest_priority_issue", sa.Text(), nullable=True),
        sa.Column("highest_priority_revision", sa.Text(), nullable=True),
        sa.Column("overall_comments", sa.Text(), nullable=True),
        sa.Column("major_strengths", sa.JSON(), nullable=False),
        sa.Column("major_weaknesses", sa.JSON(), nullable=False),
        sa.Column("recommended_action", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("evaluation_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "evaluation_type IN ('llm','human')", name="ck_evaluations_type"
        ),
        sa.CheckConstraint(
            "status IN ('draft','finalized','failed','reopened')",
            name="ck_evaluations_status",
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_evaluations_attempt"),
        sa.CheckConstraint("revision >= 1", name="ck_evaluations_revision"),
        sa.CheckConstraint(
            "weighted_score IS NULL OR (weighted_score >= 0 AND weighted_score <= 100)",
            name="ck_evaluations_weighted_score",
        ),
        sa.CheckConstraint(
            "assessment_version >= 1", name="ck_evaluations_assessment_version"
        ),
        sa.CheckConstraint(
            "length(assessment_content_hash) = 64",
            name="ck_evaluations_assessment_content_hash",
        ),
        sa.UniqueConstraint(
            "question_id",
            "evaluation_type",
            "evaluator_identity",
            "attempt",
            name="uq_evaluation_attempt",
        ),
    )
    op.create_index(
        "ix_evaluations_question_type",
        "evaluations",
        ["question_id", "evaluation_type"],
    )

    op.create_table(
        "evaluation_criteria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.Integer(),
            sa.ForeignKey("evaluations.id"),
            nullable=False,
        ),
        sa.Column("criterion_key", sa.String(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("suggested_modification", sa.Text(), nullable=True),
        sa.Column("issue_flags", sa.JSON(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("weaknesses", sa.JSON(), nullable=False),
        sa.Column("suggested_improvements", sa.JSON(), nullable=False),
        sa.Column("suggested_modifications", sa.JSON(), nullable=False),
        sa.CheckConstraint(CRITERION_KEY_SQL, name="ck_evaluation_criteria_key"),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 1 AND score <= 5)",
            name="ck_evaluation_criteria_score",
        ),
        sa.UniqueConstraint(
            "evaluation_id",
            "criterion_key",
            name="uq_evaluation_criteria_key",
        ),
    )

    op.create_table(
        "evaluation_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.Integer(),
            sa.ForeignKey("evaluations.id"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision >= 1", name="ck_evaluation_revisions_revision"
        ),
        sa.UniqueConstraint(
            "evaluation_id",
            "revision",
            name="uq_evaluation_revisions_revision",
        ),
    )

    op.create_table(
        "evaluation_access_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "human_evaluation_id",
            sa.Integer(),
            sa.ForeignKey("evaluations.id"),
            nullable=False,
        ),
        sa.Column(
            "llm_evaluation_id",
            sa.Integer(),
            sa.ForeignKey("evaluations.id"),
            nullable=False,
        ),
        sa.Column("reviewer_id", sa.String(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opened_before_finalization", sa.Boolean(), nullable=False),
        sa.UniqueConstraint(
            "human_evaluation_id",
            "llm_evaluation_id",
            "reviewer_id",
            name="uq_evaluation_first_access",
        ),
    )


def downgrade() -> None:
    op.drop_table("evaluation_access_events")
    op.drop_table("evaluation_revisions")
    op.drop_table("evaluation_criteria")
    op.drop_index("ix_evaluations_question_type", table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_index(
        "ix_assessment_questions_content_hash",
        table_name="assessment_questions",
    )
    op.drop_table("assessment_questions")

    op.drop_constraint(
        "ck_model_call_usages_stage", "model_call_usages", type_="check"
    )
    op.create_check_constraint(
        "ck_model_call_usages_stage",
        "model_call_usages",
        LEGACY_USAGE_STAGE_SQL,
    )

    op.drop_column("runs", "progress_message")
    op.drop_column("runs", "viewer_ready_at")
    op.drop_constraint("ck_runs_status", "runs", type_="check")
    op.execute(
        "UPDATE runs SET status = CASE status "
        "WHEN 'preparing_prompt' THEN 'pending' "
        "WHEN 'generating_assessment' THEN 'generating' "
        "WHEN 'validating_assessment' THEN 'generating' "
        "WHEN 'evaluating_quality' THEN 'documenting' "
        "WHEN 'saving_results' THEN 'documenting' "
        "WHEN 'generation_failed' THEN 'error' "
        "WHEN 'evaluation_failed' THEN 'error' "
        "ELSE status END"
    )
    op.create_check_constraint("ck_runs_status", "runs", LEGACY_RUN_STATUS_SQL)
