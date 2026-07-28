"""Converge experiment, execution, prompt, and assessment contracts."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

import sqlalchemy as sa
from alembic import context, op


revision = "20260727_02"
down_revision = "20260727_01"
branch_labels = None
depends_on = None


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _objective_array(value: object) -> list[str]:
    if isinstance(value, str):
        if not value.strip():
            raise RuntimeError("blank historical learning objectives cannot be migrated")
        return [value]
    if isinstance(value, list) and value and all(
        isinstance(item, str) and item.strip() for item in value
    ):
        return value
    raise RuntimeError(f"unsupported historical learning objectives: {value!r}")


def _generated_json_conflicts(legacy: object, parsed: object) -> bool:
    return _canonical_json(legacy) != _canonical_json(parsed)


def _columns(connection, table: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(connection).get_columns(table)
    }


def _normalize_legacy_payload(value: object) -> object:
    if not isinstance(value, dict) or not isinstance(value.get("questions"), list):
        return value
    payload = deepcopy(value)
    payload.pop("traceability", None)
    for question in payload["questions"]:
        if not isinstance(question, dict):
            continue
        question.pop("traceability", None)
        metadata = question.get("metadata")
        if isinstance(metadata, dict):
            for field in (
                "intended_assessment_setting",
                "prompt_template_id",
                "actual_prompt_id",
                "output_id",
                "final_question_id",
                "id_requirements",
            ):
                metadata.pop(field, None)
            if "estimated_time_minutes" not in metadata:
                estimate = metadata.pop("estimated_time", None)
                match = re.match(r"\s*(\d+)", estimate or "")
                if match:
                    metadata["estimated_time_minutes"] = int(match.group(1))
            objectives = metadata.get("learning_objectives")
            if isinstance(objectives, str):
                metadata["learning_objectives"] = [objectives]
        if "quality_checks" not in question and "quality_check" in question:
            question["quality_checks"] = question.pop("quality_check")
        question.setdefault("equations", [])
    return payload


def _migrate_learning_objectives(connection) -> None:
    op.add_column(
        "experiments",
        sa.Column("learning_objectives_v2", sa.JSON(), nullable=True),
    )
    rows = connection.execute(
        sa.text("SELECT id, learning_objectives FROM experiments")
    ).mappings()
    update = sa.text(
        "UPDATE experiments SET learning_objectives_v2=:value WHERE id=:id"
    ).bindparams(sa.bindparam("value", type_=sa.JSON()))
    for row in rows:
        connection.execute(
            update,
            {"id": row["id"], "value": _objective_array(row["learning_objectives"])},
        )
    op.alter_column("experiments", "learning_objectives_v2", nullable=False)
    op.drop_column("experiments", "learning_objectives")
    op.alter_column(
        "experiments",
        "learning_objectives_v2",
        new_column_name="learning_objectives",
    )


def _reconcile_generated_json(connection) -> None:
    if "generated_json" not in _columns(connection, "runs"):
        return
    assessments = {
        row["run_id"]: row
        for row in connection.execute(
            sa.text("SELECT run_id, parsed_json FROM assessments")
        ).mappings()
    }
    legacy_rows = list(
        connection.execute(
            sa.text(
                "SELECT id, generated_json, created_at FROM runs "
                "WHERE generated_json IS NOT NULL"
            )
        ).mappings()
    )
    conflicts = []
    insert = sa.text(
        """
        INSERT INTO assessments
          (run_id, raw_response_text, parsed_json, output_hash, schema_version,
           validation_status, validation_issues, recovery_actions,
           parsed_json_hash, created_at)
        VALUES
          (:run_id, :raw, :parsed, :output_hash, 'legacy-generated-json',
           'valid', :issues, :actions, :parsed_hash, :created_at)
        """
    ).bindparams(
        sa.bindparam("parsed", type_=sa.JSON()),
        sa.bindparam("issues", type_=sa.JSON()),
        sa.bindparam("actions", type_=sa.JSON()),
    )
    for row in legacy_rows:
        existing = assessments.get(row["id"])
        if existing is not None:
            if _generated_json_conflicts(row["generated_json"], existing["parsed_json"]):
                conflicts.append(row["id"])
            continue
        raw = _canonical_json(row["generated_json"])
        connection.execute(
            insert,
            {
                "run_id": row["id"],
                "raw": raw,
                "parsed": row["generated_json"],
                "output_hash": _sha256_text(raw),
                "issues": [],
                "actions": [],
                "parsed_hash": _sha256_text(raw),
                "created_at": row["created_at"],
            },
        )
    if conflicts:
        raise RuntimeError(
            "conflicting runs.generated_json and assessments.parsed_json for run IDs "
            + ", ".join(str(item) for item in sorted(conflicts))
        )
    op.drop_column("runs", "generated_json")


def _add_execution_fields(connection) -> None:
    op.add_column("runs", sa.Column("execution_config", sa.JSON(), nullable=True))
    rows = connection.execute(
        sa.text(
            "SELECT id, provider, model, temperature, top_p, seed, max_tokens, "
            "model_settings FROM runs"
        )
    ).mappings()
    update = sa.text(
        "UPDATE runs SET execution_config=:snapshot WHERE id=:id"
    ).bindparams(sa.bindparam("snapshot", type_=sa.JSON()))
    for row in rows:
        model_settings = row["model_settings"] or {}
        effective = {
            "provider": row["provider"] or model_settings.get("provider") or "legacy-unknown",
            "model": row["model"] or model_settings.get("model") or "legacy-unknown",
            "temperature": row["temperature"],
            "top_p": row["top_p"],
            "seed": row["seed"],
            "max_output_tokens": row["max_tokens"],
            "provider_settings": model_settings.get("provider_settings", {}),
        }
        connection.execute(
            update,
            {
                "id": row["id"],
                "snapshot": {
                    "schema_version": "legacy-1",
                    "requested": {},
                    "effective": effective,
                },
            },
        )
    op.alter_column("runs", "execution_config", nullable=False)

    for name, column in (
        ("execution_system_prompt", sa.Text()),
        ("execution_user_message", sa.Text()),
        ("execution_schema_version", sa.String()),
    ):
        op.add_column("prompts", sa.Column(name, column, nullable=True))
    connection.execute(
        sa.text(
            """
            UPDATE prompts
            SET execution_system_prompt=actual_prompt,
                execution_user_message=generation_context,
                execution_schema_version='legacy-incomplete'
            """
        )
    )
    for name in (
        "execution_system_prompt",
        "execution_user_message",
        "execution_schema_version",
    ):
        op.alter_column("prompts", name, nullable=False)


def _normalize_assessments(connection) -> None:
    update = sa.text(
        """
        UPDATE assessments
        SET parsed_json=:parsed, parsed_json_hash=:parsed_hash,
            schema_version='2'
        WHERE id=:id
        """
    ).bindparams(sa.bindparam("parsed", type_=sa.JSON()))
    for row in connection.execute(
        sa.text("SELECT id, parsed_json FROM assessments WHERE parsed_json IS NOT NULL")
    ).mappings():
        parsed = _normalize_legacy_payload(row["parsed_json"])
        connection.execute(
            update,
            {
                "id": row["id"],
                "parsed": parsed,
                "parsed_hash": _sha256_text(_canonical_json(parsed)),
            },
        )


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("contract convergence requires online evidence checks")
    connection = op.get_bind()
    _reconcile_generated_json(connection)
    _migrate_learning_objectives(connection)
    for column in ("description", "topic_area", "research_question"):
        if column in _columns(connection, "experiments"):
            op.drop_column("experiments", column)
    _add_execution_fields(connection)
    _normalize_assessments(connection)


def downgrade() -> None:
    op.add_column("experiments", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("experiments", sa.Column("topic_area", sa.String(), nullable=True))
    op.add_column(
        "experiments", sa.Column("research_question", sa.Text(), nullable=True)
    )
    for name in (
        "execution_schema_version",
        "execution_user_message",
        "execution_system_prompt",
    ):
        op.drop_column("prompts", name)
    op.drop_column("runs", "execution_config")
