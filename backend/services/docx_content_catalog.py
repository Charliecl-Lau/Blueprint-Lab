"""Immutable, canonical index of assessment content used by DOCX tools."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional, Union


_EQ_REF = re.compile(r"\[\[EQ:([A-Za-z0-9_-]+)\]\]")


class ContentCatalogError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _question_id(question: Mapping[str, Any], ordinal: int) -> str:
    trace = question.get("traceability") or {}
    value = trace.get("assessment_question_id", question.get("id", ordinal + 1))
    return str(value)


@dataclass(frozen=True)
class DocxContentCatalog:
    _payload: Mapping[str, Any]
    _text: Mapping[str, str]
    _questions: Mapping[str, Mapping[str, Any]]
    _equations: Mapping[tuple[str, str], Mapping[str, Any]]
    canonical_bytes: bytes
    sha256: str

    @classmethod
    def from_assessment(
        cls, assessment: Any, *, expected_sha256: Optional[str] = None
    ) -> "DocxContentCatalog":
        if hasattr(assessment, "model_dump"):
            assessment = assessment.model_dump(mode="json", exclude_none=False)
        if not isinstance(assessment, dict):
            raise ContentCatalogError("assessment must be a JSON object")
        payload = copy.deepcopy(assessment)
        questions = payload.get("questions")
        if not isinstance(questions, list) or not questions:
            raise ContentCatalogError("assessment must contain questions")

        texts: dict[str, str] = {}
        indexed_questions: dict[str, Mapping[str, Any]] = {}
        equations: dict[tuple[str, str], Mapping[str, Any]] = {}
        traceability = payload.get("traceability") or {}
        for key, value in sorted(traceability.items()):
            if isinstance(value, (str, int, float, bool)):
                texts[f"assessment.traceability.{key}"] = str(value)
        for key, value in sorted((payload.get("metadata") or {}).items()):
            if isinstance(value, list):
                for index, item in enumerate(value):
                    texts[f"assessment.metadata.{key}.{index}"] = str(item)
            elif value is not None:
                texts[f"assessment.metadata.{key}"] = str(value)

        for ordinal, question in enumerate(questions):
            if not isinstance(question, dict):
                raise ContentCatalogError("question must be an object")
            qid = _question_id(question, ordinal)
            if qid in indexed_questions:
                raise ContentCatalogError(f"duplicate question ID: {qid}")
            indexed_questions[qid] = MappingProxyType(copy.deepcopy(question))
            prefix = f"question.{qid}"
            metadata = question.get("metadata") or {}
            for key, value in sorted(metadata.items()):
                if isinstance(value, list):
                    for index, item in enumerate(value):
                        texts[f"{prefix}.metadata.{key}.{index}"] = str(item)
                elif value is not None:
                    texts[f"{prefix}.metadata.{key}"] = str(value)
            title = metadata.get("question_title")
            if title is not None:
                texts[f"{prefix}.title"] = str(title)
            texts[f"{prefix}.body"] = str(question.get("body") or "")
            options = question.get("options") or []
            correct_options = []
            for index, option in enumerate(options):
                label = chr(ord("A") + index)
                texts[f"{prefix}.option.{label}.body"] = str(option.get("body") or "")
                if option.get("is_correct") is True:
                    correct_options.append(label)
            model_answer = question.get("model_answer")
            if question.get("type") == "mcq":
                if len(correct_options) != 1:
                    raise ContentCatalogError(f"question {qid} requires one correct option")
                texts[f"{prefix}.solution.correct_option"] = correct_options[0]
            elif not model_answer:
                raise ContentCatalogError(f"question {qid} requires a model answer")
            if model_answer:
                texts[f"{prefix}.solution.body"] = str(model_answer)
                for index, step in enumerate(str(model_answer).splitlines()):
                    if step.strip():
                        texts[f"{prefix}.solution.step.{index}"] = step
            solution = question.get("solution") or {}
            if isinstance(solution, dict):
                for key, value in sorted(solution.items()):
                    if isinstance(value, list):
                        for index, item in enumerate(value):
                            texts[f"{prefix}.solution.{key}.{index}"] = str(item)
                    elif value is not None:
                        texts[f"{prefix}.solution.{key}"] = str(value)
            for index, revision in enumerate(question.get("revision_options") or []):
                texts[f"{prefix}.revision_option.{index}"] = str(revision)
            for index, check in enumerate(question.get("quality_checks") or []):
                for key in ("criterion", "rating", "comment"):
                    if key in check:
                        texts[f"{prefix}.quality_check.{index}.{key}"] = str(check[key])
            for key, value in sorted((question.get("traceability") or {}).items()):
                texts[f"{prefix}.traceability.{key}"] = str(value)

            equation_ids = set()
            for equation in question.get("equations") or []:
                equation_id = str(equation.get("equation_id") or equation.get("label") or "")
                if not equation_id or equation_id in equation_ids:
                    raise ContentCatalogError(f"duplicate equation ID in question {qid}: {equation_id}")
                equation_ids.add(equation_id)
                equations[(qid, equation_id)] = MappingProxyType(copy.deepcopy(equation))
            referenced = {
                match
                for value in texts.values()
                for match in _EQ_REF.findall(value)
            }
            # Scope the check to references belonging to the current question.
            current_values = [value for ref, value in texts.items() if ref.startswith(prefix + ".")]
            current_refs = {match for value in current_values for match in _EQ_REF.findall(value)}
            dangling = current_refs - equation_ids
            if dangling:
                raise ContentCatalogError(f"question {qid} has dangling equation references: {sorted(dangling)}")

        representation = {
            "schema_version": "docx-content-catalog-v1",
            "assessment": payload,
            "text_index": texts,
            "equation_index": [
                {"question_id": qid, "equation_id": eid, "equation": dict(value)}
                for (qid, eid), value in sorted(equations.items())
            ],
        }
        canonical_bytes = _canonical(representation)
        digest = hashlib.sha256(canonical_bytes).hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise ContentCatalogError("content catalog hash drift")
        return cls(
            MappingProxyType(payload),
            MappingProxyType(texts),
            MappingProxyType(indexed_questions),
            MappingProxyType(equations),
            canonical_bytes,
            digest,
        )

    @property
    def question_ids(self) -> tuple[str, ...]:
        return tuple(self._questions)

    @property
    def content_refs(self) -> tuple[str, ...]:
        return tuple(sorted(self._text))

    @property
    def equation_ids(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._equations))

    def resolve_text(self, content_ref: str) -> str:
        try:
            return self._text[content_ref]
        except KeyError as exc:
            raise ContentCatalogError(f"unknown content_ref: {content_ref}") from exc

    def resolve_question(self, question_id: Union[str, int]) -> dict:
        try:
            return copy.deepcopy(dict(self._questions[str(question_id)]))
        except KeyError as exc:
            raise ContentCatalogError(f"unknown question ID: {question_id}") from exc

    def resolve_equation(self, question_id: Union[str, int], equation_id: str) -> dict:
        try:
            return copy.deepcopy(dict(self._equations[(str(question_id), equation_id)]))
        except KeyError as exc:
            raise ContentCatalogError(
                f"unknown equation: question={question_id}, equation={equation_id}"
            ) from exc

    def clone_assessment(self) -> dict:
        return copy.deepcopy(dict(self._payload))

    def provider_index(self) -> dict:
        """Content-free structural index safe to combine with tool declarations."""
        return {
            "catalog_sha256": self.sha256,
            "content_refs": [
                {"content_ref": ref, "character_count": len(self._text[ref])}
                for ref in sorted(self._text)
            ],
            "questions": [
                {
                    "question_id": qid,
                    "type": self._questions[qid].get("type"),
                    "equations": [
                        {
                            "equation_id": equation_id,
                            "location": equation.get("location"),
                        }
                        for (question_id, equation_id), equation in sorted(self._equations.items())
                        if question_id == qid
                    ],
                }
                for qid in self.question_ids
            ],
        }
