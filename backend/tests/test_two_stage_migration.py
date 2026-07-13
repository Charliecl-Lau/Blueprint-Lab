import importlib
from types import SimpleNamespace


migration = importlib.import_module("backend.migrations.versions.20260712_01_two_stage_prompts")


def test_drop_check_constraint_if_present_uses_existing_database_name(monkeypatch):
    dropped = []

    class FakeConnection:
        def execute(self, statement, params):
            assert params == {"table_name": "prompts"}
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ["prompts_prompt_hash_check"]))

    monkeypatch.setattr(migration.op, "get_bind", lambda: FakeConnection())
    monkeypatch.setattr(migration.op, "drop_constraint", lambda name, table, type_: dropped.append((name, table, type_)))

    migration._drop_check_constraint_if_present(
        "prompts",
        ("ck_prompts_prompt_hash", "prompts_prompt_hash_check"),
    )

    assert dropped == [("prompts_prompt_hash_check", "prompts", "check")]


def test_drop_check_constraint_if_present_skips_missing_constraint(monkeypatch):
    dropped = []

    class FakeConnection:
        def execute(self, statement, params):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    monkeypatch.setattr(migration.op, "get_bind", lambda: FakeConnection())
    monkeypatch.setattr(migration.op, "drop_constraint", lambda name, table, type_: dropped.append((name, table, type_)))

    migration._drop_check_constraint_if_present(
        "prompts",
        ("ck_prompts_prompt_hash", "prompts_prompt_hash_check"),
    )

    assert dropped == []
