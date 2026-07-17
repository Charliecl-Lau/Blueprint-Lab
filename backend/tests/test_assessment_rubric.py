import pytest

from backend.services.assessment_rubric import (
    CRITERION_KEYS,
    RUBRIC_SNAPSHOT,
    RUBRIC_VERSION,
    calculate_evaluation,
)


def test_rubric_snapshot_preserves_exact_version_weights_and_anchors():
    assert RUBRIC_VERSION == "2026-07-16"
    assert [item["key"] for item in RUBRIC_SNAPSHOT["criteria"]] == list(CRITERION_KEYS)
    assert [item["weight"] for item in RUBRIC_SNAPSHOT["criteria"]] == [30, 25, 10, 25, 10]
    assert all(set(item["anchors"]) == {"1", "3", "5"} for item in RUBRIC_SNAPSHOT["criteria"])


@pytest.mark.parametrize(
    ("scores", "weighted", "gate", "decision"),
    [
        ([5, 5, 5, 5, 5], 100.0, "PASS", "Instructor-ready"),
        ([4, 4, 4, 4, 4], 80.0, "PASS", "Strong – minor revision"),
        ([3, 3, 3, 3, 3], 60.0, "PASS", "Substantial revision"),
        ([2, 5, 5, 5, 5], 82.0, "FAIL", "Not ready – critical issue"),
    ],
)
def test_calculation_applies_weights_thresholds_and_critical_gate(scores, weighted, gate, decision):
    result = calculate_evaluation(dict(zip(CRITERION_KEYS, scores)))
    assert result.weighted_score == weighted
    assert result.critical_gate == gate
    assert result.overall_decision == decision


@pytest.mark.parametrize("score", [0, 6, 2.5, True])
def test_calculation_rejects_values_outside_integer_scale(score):
    values = {key: 3 for key in CRITERION_KEYS}
    values[CRITERION_KEYS[0]] = score
    with pytest.raises(ValueError, match="integer from 1 through 5"):
        calculate_evaluation(values)


def test_calculation_requires_every_criterion():
    with pytest.raises(ValueError, match="all five rubric criteria"):
        calculate_evaluation({CRITERION_KEYS[0]: 5})


def test_clarity_text_matches_authoritative_markdown():
    clarity = next(item for item in RUBRIC_SNAPSHOT["criteria"] if item["key"] == "clarity_solution")
    assert "faithful compliance with the instructor prompt" in clarity["description"]
    assert "fully compliant with the request" in clarity["anchors"]["5"]
