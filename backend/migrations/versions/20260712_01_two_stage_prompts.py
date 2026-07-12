"""Persist both LLM call envelopes and structure-call metadata."""

from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa
from alembic import context, op


revision = "20260712_01"
down_revision = "20260711_01"
branch_labels = None
depends_on = None


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError(
            "offline SQL migration is refused because exact prompt envelope hashing "
            "requires Python; run `python -m alembic upgrade head` online with DATABASE_URL set"
        )

    op.drop_constraint("ck_prompts_prompt_hash", "prompts", type_="check")
    op.alter_column("prompts", "system_prompt", new_column_name="structure_system_prompt")
    op.alter_column("prompts", "final_prompt", new_column_name="actual_prompt")
    op.alter_column("prompts", "template_version", new_column_name="structure_prompt_version")
    op.alter_column("prompts", "generator_version", new_column_name="actual_prompt_generator_version")
    op.alter_column("prompts", "prompt_hash", new_column_name="actual_prompt_hash")

    op.add_column("prompts", sa.Column("structure_input", sa.Text(), nullable=True))
    op.add_column("prompts", sa.Column("structure_request_id", sa.String(), nullable=True))
    op.add_column("prompts", sa.Column("structure_model", sa.String(), nullable=True))
    op.add_column("prompts", sa.Column("structure_model_version", sa.String(), nullable=True))
    op.add_column("prompts", sa.Column("structure_finish_reason", sa.String(), nullable=True))
    op.add_column("prompts", sa.Column("structure_duration_ms", sa.Integer(), nullable=True))
    op.add_column("prompts", sa.Column("generation_context", sa.Text(), nullable=True))
    op.add_column("prompts", sa.Column("generation_envelope_hash", sa.String(length=64), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("""
        SELECT p.id, p.prompt_structure, p.structure_system_prompt, p.actual_prompt,
               p.structure_prompt_version, p.actual_prompt_generator_version,
               r.model_settings
        FROM prompts p JOIN runs r ON r.id = p.run_id
        ORDER BY p.id
    """)).mappings()
    update = sa.text("""
        UPDATE prompts
        SET structure_input=:structure_input, actual_prompt_hash=:actual_prompt_hash,
            generation_context=:generation_context,
            generation_envelope_hash=:generation_envelope_hash
        WHERE id=:id
    """)
    for row in rows:
        structure_input = ""
        generation_context = ""
        model_settings = row["model_settings"] or {}
        actual_hash = _hash({
            "structure_system_prompt": row["structure_system_prompt"],
            "structure_input": structure_input,
            "actual_prompt": row["actual_prompt"],
            "prompt_structure": row["prompt_structure"],
            "structure_prompt_version": row["structure_prompt_version"],
            "actual_prompt_generator_version": row["actual_prompt_generator_version"],
            "model_settings": model_settings,
        })
        source_hashes = [item[0] for item in connection.execute(sa.text("""
            SELECT included_text_hash FROM run_source_documents
            WHERE run_id = (SELECT run_id FROM prompts WHERE id=:id)
            ORDER BY ordinal, id
        """), {"id": row["id"]})]
        generation_hash = _hash({
            "actual_prompt": row["actual_prompt"],
            "generation_context": generation_context,
            "model_settings": model_settings,
            "source_hashes": source_hashes,
        })
        connection.execute(update, {
            "id": row["id"], "structure_input": structure_input,
            "actual_prompt_hash": actual_hash, "generation_context": generation_context,
            "generation_envelope_hash": generation_hash,
        })

    for column in ("structure_input", "generation_context", "generation_envelope_hash"):
        op.alter_column("prompts", column, nullable=False)
    op.create_check_constraint("ck_prompts_actual_prompt_hash", "prompts", "length(actual_prompt_hash) = 64")
    op.create_check_constraint("ck_prompts_generation_envelope_hash", "prompts", "length(generation_envelope_hash) = 64")


def downgrade() -> None:
    raise RuntimeError("lossless downgrade is impossible after two-stage prompt evidence is introduced")
