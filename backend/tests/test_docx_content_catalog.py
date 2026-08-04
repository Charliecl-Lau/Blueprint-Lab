import copy

import pytest

from backend.services.docx_content_catalog import ContentCatalogError, DocxContentCatalog


def _payload():
    return {
        "traceability": {"assessment_id": 7, "assessment_version": 1},
        "questions": [{
            "type": "mcq",
            "traceability": {"assessment_question_id": 20, "ordinal": 0},
            "metadata": {"question_title": "Expansion"},
            "body": "Evaluate [[EQ:alpha]].",
            "options": [
                {"body": "One", "is_correct": True},
                {"body": "Two", "is_correct": False},
            ],
            "model_answer": "One because [[EQ:work]].",
            "equations": [
                {"label": "alpha", "math": {"type": "symbol", "name": "alpha"}, "expression": "alpha", "location": "question"},
                {"label": "work", "math": {"type": "symbol", "name": "W"}, "expression": "W", "location": "solution"},
            ],
            "quality_checks": [{"criterion": "Clear", "rating": 5, "comment": "Yes"}],
            "revision_options": ["Use another alloy", "Change temperature"],
        }],
    }


def test_catalog_is_deterministic_immutable_and_resolvable():
    source = _payload()
    catalog = DocxContentCatalog.from_assessment(source)
    source["questions"][0]["body"] = "mutated"
    assert catalog.resolve_text("question.20.body") == "Evaluate [[EQ:alpha]]."
    assert catalog.resolve_text("question.20.option.A.body") == "One"
    assert catalog.resolve_equation("20", "alpha")["expression"] == "alpha"
    assert catalog.canonical_bytes == DocxContentCatalog.from_assessment(_payload()).canonical_bytes
    assert len(catalog.sha256) == 64


@pytest.mark.parametrize("mutation", ["duplicate_question", "duplicate_equation", "dangling", "missing_answer"])
def test_catalog_rejects_invalid_assessed_content(mutation):
    payload = _payload()
    if mutation == "duplicate_question":
        payload["questions"].append(copy.deepcopy(payload["questions"][0]))
    elif mutation == "duplicate_equation":
        payload["questions"][0]["equations"].append(copy.deepcopy(payload["questions"][0]["equations"][0]))
    elif mutation == "dangling":
        payload["questions"][0]["body"] = "[[EQ:missing]]"
    else:
        payload["questions"][0]["options"][0]["is_correct"] = False
    with pytest.raises(ContentCatalogError):
        DocxContentCatalog.from_assessment(payload)
