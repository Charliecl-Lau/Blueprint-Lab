import importlib


migration = importlib.import_module(
    "backend.migrations.versions.20260717_01_assessment_evaluations"
)


class FakeResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class FakeConnection:
    def __init__(self, values):
        self._values = values

    def execute(self, statement, parameters):
        assert parameters == {"table_name": "runs"}
        return FakeResult(self._values)


def test_drop_check_constraint_accepts_legacy_generated_name(monkeypatch):
    dropped = []
    monkeypatch.setattr(
        migration.op,
        "get_bind",
        lambda: FakeConnection(["runs_status_check"]),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_constraint",
        lambda name, table, type_: dropped.append((name, table, type_)),
    )

    migration._drop_check_constraint_if_present(
        "runs", ("ck_runs_status", "runs_status_check")
    )

    assert dropped == [("runs_status_check", "runs", "check")]


def test_drop_check_constraint_prefers_canonical_name(monkeypatch):
    dropped = []
    monkeypatch.setattr(
        migration.op,
        "get_bind",
        lambda: FakeConnection(["ck_runs_status", "runs_status_check"]),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_constraint",
        lambda name, table, type_: dropped.append((name, table, type_)),
    )

    migration._drop_check_constraint_if_present(
        "runs", ("ck_runs_status", "runs_status_check")
    )

    assert dropped == [("ck_runs_status", "runs", "check")]
