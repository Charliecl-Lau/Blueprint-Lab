import importlib

import pytest


migration = importlib.import_module(
    "backend.migrations.versions.20260727_02_contract_convergence"
)


def test_objective_array_preserves_historical_text_as_one_item():
    assert migration._objective_array("First objective; second phrase") == [
        "First objective; second phrase"
    ]
    assert migration._objective_array(["First", "Second"]) == ["First", "Second"]


@pytest.mark.parametrize("value", [None, "", "   ", [], ["Valid", " "]])
def test_objective_array_refuses_missing_or_ambiguous_values(value):
    with pytest.raises(RuntimeError):
        migration._objective_array(value)


def test_generated_json_conflict_detection_accepts_equivalent_json_only():
    legacy = {"questions": [{"body": "Q"}]}
    assert migration._generated_json_conflicts(legacy, legacy) is False
    assert migration._generated_json_conflicts(legacy, {"questions": []}) is True
