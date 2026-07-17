# Assessment Grading Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically evaluate every validated assessment question with the approved rubric, expose generated questions in the Viewer while evaluation continues, live-update evaluation token usage, and provide a human-first grading and comparison workflow.

**Architecture:** Preserve each run’s `Assessment` as immutable provider evidence, create stable `AssessmentQuestion` rows after validation, and store human and LLM evaluations in normalized records with criterion rows and revision/access history. Split LLM evaluation into an asynchronous Celery task so `viewer_ready_at` can unlock the Viewer before final completion; run snapshots update the Viewer’s status and token counter until evaluation and result saving finish.

**Tech Stack:** Python 3.9+, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, Celery/Redis, Google GenAI, pytest, React 19, TypeScript 6, React Router 7, Zustand, Vitest, Testing Library, jest-axe, Playwright.

## Global Constraints

- Rubric version is exactly `2026-07-16`; weights are `30/25/10/25/10` and Technical Correctness & Solvability below 3 overrides the weighted decision.
- Generated assessment JSON and content hashes are immutable; evaluation never rewrites a question or model answer.
- Viewer access begins after validation and stable question persistence; grading access begins only after every LLM evaluation is finalized.
- LLM content is read-only and collapsed by default before the expanded Human Assessment; comparison follows and is also collapsed by default.
- There is no Assessment Summary section on the grading page.
- Evaluation calls and retries use the existing usage ledger with stage `evaluation`; all reported usage remains in run totals.
- Human and LLM evaluations are separate records, and reviewer/evaluator records never overwrite one another.
- Every commit has an imperative subject plus a paragraph explaining what changed and why; never add attribution trailers.
- Preserve unrelated changes already present in the user’s main worktree.

---

### Task 1: Authoritative rubric and calculation service

**Files:**
- Create: `backend/services/assessment_rubric.py`
- Create: `backend/tests/test_assessment_rubric.py`

**Interfaces:**
- Produces: `RUBRIC_VERSION`, `RUBRIC_SNAPSHOT`, `CRITERION_KEYS`, `calculate_evaluation(scores: Mapping[str, int]) -> EvaluationCalculation`.
- `EvaluationCalculation` exposes `weighted_score`, `critical_gate`, `overall_decision`, and `instructor_readiness`.

- [ ] **Step 1: Write failing rubric contract tests**

```python
# backend/tests/test_assessment_rubric.py
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


@pytest.mark.parametrize("score", [0, 6, 2.5])
def test_calculation_rejects_values_outside_integer_scale(score):
    values = {key: 3 for key in CRITERION_KEYS}
    values[CRITERION_KEYS[0]] = score
    with pytest.raises(ValueError, match="integer from 1 through 5"):
        calculate_evaluation(values)


def test_calculation_requires_every_criterion():
    with pytest.raises(ValueError, match="all five rubric criteria"):
        calculate_evaluation({CRITERION_KEYS[0]: 5})
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest backend/tests/test_assessment_rubric.py -v`

Expected: collection fails with `ModuleNotFoundError: backend.services.assessment_rubric`.

- [ ] **Step 3: Implement the exact rubric and pure calculator**

```python
# backend/services/assessment_rubric.py
from dataclasses import dataclass
from typing import Mapping

RUBRIC_VERSION = "2026-07-16"
CRITERION_KEYS = (
    "technical_correctness",
    "course_alignment",
    "blooms_alignment",
    "clarity_solution",
    "materials_context",
)

RUBRIC_SNAPSHOT = {
    "version": RUBRIC_VERSION,
    "criteria": [
        {
            "key": "technical_correctness",
            "title": "Technical Correctness & Solvability",
            "weight": 30,
            "covers": "Accuracy + Solvability",
            "description": "Thermodynamic correctness; valid equations, assumptions, units, signs, numerical results, and physical interpretation; sufficient and internally consistent data for a unique intended answer.",
            "comment_prompt": "Which equation, assumption, unit, datum, sign convention, or result needs correction or clarification?",
            "anchors": {
                "1": "Contains a substantive error, contradiction, missing essential information, or cannot be solved reliably as written.",
                "3": "Mostly correct and solvable, but has a minor error, implicit assumption, or local inconsistency that should be repaired.",
                "5": "Correct, precise, self-contained, internally consistent, uniquely answerable where intended, and physically defensible.",
            },
        },
        {
            "key": "course_alignment",
            "title": "Course Alignment & Concept Bridge",
            "weight": 25,
            "covers": "Course Alignment + Concept Bridge",
            "description": "Alignment with MSE202 preparation, MSE302 target knowledge, requested difficulty and setting; explicit and meaningful transfer from the prerequisite concept to the later concept.",
            "comment_prompt": "What exactly is transferred from MSE202 to MSE302, and must students use that connection to solve the question?",
            "anchors": {
                "1": "Off-level, off-topic, or the two course concepts are merely named, isolated, or connected inaccurately.",
                "3": "Generally appropriate with a valid but somewhat superficial bridge, limited scope mismatch, or uneven emphasis.",
                "5": "Well matched to student preparation and assessment setting; the MSE202–MSE302 bridge is explicit, central, and thermodynamically meaningful.",
            },
        },
        {
            "key": "blooms_alignment",
            "title": "Bloom’s Taxonomy Alignment & Assessment Design",
            "weight": 10,
            "covers": "Bloom’s Taxonomy Alignment + Assessment Design",
            "description": "Match between the Bloom’s taxonomy level specified in the instructor prompt and the observable work students must perform. Judge the actual reasoning required, not the action verb alone, and consider whether scaffolding, complexity, and workload suit the assessment setting.",
            "comment_prompt": "What must students actually do, and does that observable performance correspond to the Bloom’s level specified in the prompt?",
            "anchors": {
                "1": "Does not match the specified Bloom’s level. For example, the task asks only for recall or routine substitution when Analyze, Evaluate, or Create was requested, or it demands higher-order synthesis when a lower level was intended.",
                "3": "Generally matches the specified level, but the demand is mixed, over-scaffolded, or only part of the response requires performance at the target level.",
                "5": "Clearly and consistently elicits the specified Bloom’s level through observable student performance, with suitable complexity, scaffolding, and workload for the assessment setting.",
            },
        },
        {
            "key": "clarity_solution",
            "title": "Clarity, Prompt Alignment & Solution Quality",
            "weight": 25,
            "covers": "Clarity + Prompt–Output Alignment + Solution Quality",
            "description": "Clear wording, notation, data, deliverables, assumptions, constraints, and answer choices; faithful prompt compliance; complete, auditable solution and answer key.",
            "comment_prompt": "Could students interpret the task consistently, and could an instructor verify every requested requirement and every essential solution step?",
            "anchors": {
                "1": "Ambiguous or cumbersome; misses central prompt requirements; solution or key is incorrect, incomplete, or skips essential reasoning.",
                "3": "Understandable and mostly compliant, but needs minor wording, formatting, algebra, units, assumptions, or explanation improvements.",
                "5": "Concise, student-ready, fully compliant, and supported by a complete solution with assumptions, units, physical meaning, and distractor analysis where applicable.",
            },
        },
        {
            "key": "materials_context",
            "title": "Materials Science Context & Relevance",
            "weight": 10,
            "covers": "Materials Context",
            "description": "Authenticity, specificity, plausibility, and instructional value of the materials science or engineering scenario.",
            "comment_prompt": "Does the context meaningfully support the thermodynamics or an engineering interpretation rather than merely naming a material?",
            "anchors": {
                "1": "Generic, decorative, implausible, or unrelated to the thermodynamic reasoning.",
                "3": "Relevant context is present but underdeveloped or contributes little to interpretation or decision-making.",
                "5": "Authentic and specific context that motivates the analysis and helps students interpret the result in a materials engineering setting.",
            },
        },
    ],
}


@dataclass(frozen=True)
class EvaluationCalculation:
    weighted_score: float
    critical_gate: str
    overall_decision: str
    instructor_readiness: str


def calculate_evaluation(scores: Mapping[str, int]) -> EvaluationCalculation:
    if set(scores) != set(CRITERION_KEYS):
        raise ValueError("scores must contain all five rubric criteria")
    if any(not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5 for value in scores.values()):
        raise ValueError("each score must be an integer from 1 through 5")
    weights = {item["key"]: item["weight"] for item in RUBRIC_SNAPSHOT["criteria"]}
    weighted = round(sum(scores[key] * weights[key] / 5 for key in CRITERION_KEYS), 1)
    gate = "FAIL" if scores["technical_correctness"] < 3 else "PASS"
    if gate == "FAIL":
        decision = "Not ready – critical issue"
    elif weighted >= 90:
        decision = "Instructor-ready"
    elif weighted >= 80:
        decision = "Strong – minor revision"
    elif weighted >= 70:
        decision = "Usable – moderate revision"
    elif weighted >= 60:
        decision = "Substantial revision"
    else:
        decision = "Not ready"
    readiness = "Instructor-ready" if decision == "Instructor-ready" else "Revision required"
    return EvaluationCalculation(weighted, gate, decision, readiness)
```

- [ ] **Step 4: Run rubric tests and verify GREEN**

Run: `python -m pytest backend/tests/test_assessment_rubric.py -v`

Expected: all rubric tests pass.

- [ ] **Step 5: Commit the rubric contract**

```powershell
git add backend/services/assessment_rubric.py backend/tests/test_assessment_rubric.py
git commit -m "Define assessment quality rubric" -m "Encode the approved rubric version, exact criterion weights, score anchors, weighted thresholds, and technical critical gate in one tested service so human and LLM evaluations share an authoritative calculation contract."
```

### Task 2: Normalized evaluation persistence and migration

**Files:**
- Create: `backend/models/evaluation.py`
- Modify: `backend/models/run.py`
- Modify: `backend/models/__init__.py`
- Create: `backend/migrations/versions/20260717_01_assessment_evaluations.py`
- Create: `backend/tests/test_evaluation_models.py`
- Create: `backend/tests/integration/test_evaluation_migration.py`

**Interfaces:**
- Produces SQLAlchemy models `AssessmentQuestion`, `Evaluation`, `EvaluationCriterion`, `EvaluationRevision`, and `EvaluationAccessEvent`.
- Adds `Run.viewer_ready_at`, `Run.progress_message`, and the new progress status constraint.
- Adds `Assessment.questions` and `AssessmentQuestion.evaluations` relationships.

- [ ] **Step 1: Write failing model tests**

```python
# backend/tests/test_evaluation_models.py
import pytest
from sqlalchemy.exc import IntegrityError

from backend.models import AssessmentQuestion, Evaluation, EvaluationCriterion
from backend.services.assessment_rubric import RUBRIC_SNAPSHOT, RUBRIC_VERSION


def test_question_and_multiple_evaluators_are_stored_without_overwrite(test_db, generation_fixture):
    question = AssessmentQuestion(
        assessment_id=generation_fixture.assessment.id,
        ordinal=0,
        assessment_version=1,
        content_hash="a" * 64,
    )
    test_db.add(question)
    test_db.flush()
    first = Evaluation.from_run(
        generation_fixture,
        question=question,
        evaluation_type="human",
        evaluator_identity="reviewer-a",
        rubric_version=RUBRIC_VERSION,
        rubric_snapshot=RUBRIC_SNAPSHOT,
    )
    second = Evaluation.from_run(
        generation_fixture,
        question=question,
        evaluation_type="human",
        evaluator_identity="reviewer-b",
        rubric_version=RUBRIC_VERSION,
        rubric_snapshot=RUBRIC_SNAPSHOT,
    )
    test_db.add_all([first, second])
    test_db.commit()
    assert {item.evaluator_identity for item in question.evaluations} == {"reviewer-a", "reviewer-b"}


def test_criterion_enforces_unique_key_and_score_scale(test_db, generation_fixture):
    question = AssessmentQuestion(assessment_id=generation_fixture.assessment.id, ordinal=0, assessment_version=1, content_hash="b" * 64)
    evaluation = Evaluation.from_run(generation_fixture, question=question, evaluation_type="llm", evaluator_identity="gemini", rubric_version=RUBRIC_VERSION, rubric_snapshot=RUBRIC_SNAPSHOT)
    evaluation.criteria.extend([
        EvaluationCriterion(criterion_key="technical_correctness", score=3),
        EvaluationCriterion(criterion_key="technical_correctness", score=6),
    ])
    test_db.add(evaluation)
    with pytest.raises(IntegrityError):
        test_db.commit()
```

Also add an online PostgreSQL migration test that upgrades from `20260716_01`, asserts all five tables and indexes exist, confirms the run status and model-call stage constraints include the new values, and confirms a seeded `rubric_results` row remains unchanged.

- [ ] **Step 2: Run model tests and verify RED**

Run: `python -m pytest backend/tests/test_evaluation_models.py backend/tests/integration/test_evaluation_migration.py -v`

Expected: imports fail because the new models and migration do not exist.

- [ ] **Step 3: Add models and relationships**

Create models with these exact invariants:

```python
# backend/models/evaluation.py
class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (
        UniqueConstraint("assessment_id", "ordinal", name="uq_assessment_questions_ordinal"),
        Index("ix_assessment_questions_content_hash", "assessment_id", "content_hash"),
        CheckConstraint("ordinal >= 0"),
        CheckConstraint("assessment_version >= 1"),
        CheckConstraint("length(content_hash) = 64"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    assessment_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    assessment: Mapped["Assessment"] = relationship(back_populates="questions")
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="question")


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        CheckConstraint("evaluation_type IN ('llm','human')"),
        CheckConstraint("status IN ('draft','finalized','failed','reopened')"),
        CheckConstraint("attempt >= 1"),
        CheckConstraint("weighted_score IS NULL OR (weighted_score >= 0 AND weighted_score <= 100)"),
        UniqueConstraint("question_id", "evaluation_type", "evaluator_identity", "attempt", name="uq_evaluation_attempt"),
        Index("ix_evaluations_question_type", "question_id", "evaluation_type"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False)
    condition_id: Mapped[int] = mapped_column(ForeignKey("conditions.id"), nullable=False)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), nullable=False)
    question_id: Mapped[int] = mapped_column(ForeignKey("assessment_questions.id"), nullable=False)
    evaluation_type: Mapped[str] = mapped_column(String, nullable=False)
    evaluator_identity: Mapped[str] = mapped_column(String, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    evaluation_model: Mapped[Optional[str]] = mapped_column(String)
    evaluation_model_version: Mapped[Optional[str]] = mapped_column(String)
    rubric_version: Mapped[str] = mapped_column(String, nullable=False)
    rubric_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    prompt_template_id: Mapped[Optional[str]] = mapped_column(String)
    actual_prompt_id: Mapped[Optional[str]] = mapped_column(String)
    output_id: Mapped[Optional[str]] = mapped_column(String)
    generation_model: Mapped[Optional[str]] = mapped_column(String)
    generation_model_version: Mapped[Optional[str]] = mapped_column(String)
    prompt_design_factors: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    weighted_score: Mapped[Optional[float]] = mapped_column(Float)
    critical_gate: Mapped[Optional[str]] = mapped_column(String)
    overall_decision: Mapped[Optional[str]] = mapped_column(String)
    instructor_readiness: Mapped[Optional[str]] = mapped_column(String)
    highest_priority_issue: Mapped[Optional[str]] = mapped_column(Text)
    overall_comments: Mapped[Optional[str]] = mapped_column(Text)
    major_strengths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    major_weaknesses: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recommended_action: Mapped[Optional[str]] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    question: Mapped[AssessmentQuestion] = relationship(back_populates="evaluations")
    criteria: Mapped[list["EvaluationCriterion"]] = relationship(back_populates="evaluation", cascade="all, delete-orphan")


class EvaluationCriterion(Base):
    __tablename__ = "evaluation_criteria"
    __table_args__ = (
        UniqueConstraint("evaluation_id", "criterion_key"),
        CheckConstraint("criterion_key IN ('technical_correctness','course_alignment','blooms_alignment','clarity_solution','materials_context')"),
        CheckConstraint("score IS NULL OR (score >= 1 AND score <= 5)"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), nullable=False)
    criterion_key: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[Optional[int]] = mapped_column(Integer)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    suggested_modification: Mapped[Optional[str]] = mapped_column(Text)
    issue_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    strengths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    weaknesses: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    suggested_improvements: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    suggested_modifications: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evaluation: Mapped[Evaluation] = relationship(back_populates="criteria")
```

Implement `Evaluation.from_run(run: Run, *, question: AssessmentQuestion, evaluation_type: str, evaluator_identity: str, rubric_version: str, rubric_snapshot: dict, evaluation_model: Optional[str] = None, attempt: int = 1) -> Evaluation` to copy the run, experiment, condition, assessment, model, prompt metadata, and factor snapshot at creation time.

Add the history models with these fields and constraints:

```python
class EvaluationRevision(Base):
    __tablename__ = "evaluation_revisions"
    __table_args__ = (UniqueConstraint("evaluation_id", "revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvaluationAccessEvent(Base):
    __tablename__ = "evaluation_access_events"
    __table_args__ = (UniqueConstraint("human_evaluation_id", "llm_evaluation_id", "reviewer_id", name="uq_evaluation_first_access"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    human_evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), nullable=False)
    llm_evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    opened_before_finalization: Mapped[bool] = mapped_column(Boolean, nullable=False)
```

- [ ] **Step 4: Add and run the migration**

The migration must drop and recreate `ck_runs_status` with:

```text
('preparing_prompt','generating_assessment','validating_assessment','evaluating_quality','saving_results','complete','generation_failed','evaluation_failed')
```

It must translate legacy live values in place, add `viewer_ready_at` and `progress_message`, add `evaluation` to `ck_model_call_usages_stage`, create all normalized tables/indexes, and preserve `rubric_results`.

Run: `python -m alembic upgrade head`

Expected: migration reaches `20260717_01` without errors.

- [ ] **Step 5: Run persistence tests and verify GREEN**

Run: `python -m pytest backend/tests/test_evaluation_models.py backend/tests/integration/test_evaluation_migration.py -v`

Expected: unit tests pass; PostgreSQL test passes when configured or reports the repository’s explicit skip reason.

- [ ] **Step 6: Commit normalized persistence**

```powershell
git add backend/models backend/migrations/versions/20260717_01_assessment_evaluations.py backend/tests/test_evaluation_models.py backend/tests/integration/test_evaluation_migration.py
git commit -m "Persist normalized assessment evaluations" -m "Create stable assessment-question identities and separate evaluation, criterion, revision, and access records so human and LLM reviews remain traceable, independently versioned, and safe for multiple evaluators."
```

### Task 3: Question persistence, LLM schema, and evaluation service

**Files:**
- Create: `backend/schemas/evaluation_schema.py`
- Create: `backend/services/assessment_evaluation.py`
- Create: `backend/tests/test_assessment_evaluation.py`
- Modify: `backend/config.py`
- Modify: `.env.example`

**Interfaces:**
- Produces `persist_assessment_questions(db, assessment) -> list[AssessmentQuestion]`.
- Produces `evaluate_question(db, run, question, llm, progress) -> Evaluation`.
- Produces Pydantic request/response schemas for criterion results, drafts, finalization, and comparison.

- [ ] **Step 1: Write failing evaluator service tests**

```python
# backend/tests/test_assessment_evaluation.py
from backend.models import Evaluation
from backend.services.assessment_evaluation import evaluate_question, persist_assessment_questions


def test_persist_questions_uses_canonical_content_without_mutating_assessment(test_db, generation_fixture):
    before = generation_fixture.assessment.parsed_json.copy()
    questions = persist_assessment_questions(test_db, generation_fixture.assessment)
    assert [item.ordinal for item in questions] == list(range(len(before["questions"])))
    assert all(len(item.content_hash) == 64 for item in questions)
    assert generation_fixture.assessment.parsed_json == before


def test_evaluate_question_saves_finalized_llm_criteria_and_authoritative_total(test_db, generation_fixture, fake_llm):
    question = persist_assessment_questions(test_db, generation_fixture.assessment)[0]
    fake_llm.result.raw_text = VALID_EVALUATION_JSON
    evaluation = evaluate_question(test_db, generation_fixture, question, fake_llm, lambda message: None)
    assert evaluation.evaluation_type == "llm"
    assert evaluation.status == "finalized"
    assert evaluation.weighted_score == 82.0
    assert evaluation.critical_gate == "FAIL"
    assert evaluation.overall_decision == "Not ready – critical issue"
    assert len(evaluation.criteria) == 5
    assert generation_fixture.assessment.parsed_json["questions"][0] == ORIGINAL_QUESTION


def test_invalid_evaluator_output_creates_failed_record_without_changing_question(test_db, generation_fixture, fake_llm):
    question = persist_assessment_questions(test_db, generation_fixture.assessment)[0]
    fake_llm.result.raw_text = '{"criteria": []}'
    with pytest.raises(EvaluationValidationError):
        evaluate_question(test_db, generation_fixture, question, fake_llm, lambda message: None)
    failed = test_db.query(Evaluation).filter_by(question_id=question.id, evaluation_type="llm").one()
    assert failed.status == "failed"
```

Assert separately that the evaluator user message contains the immutable question, model answer, assessment content hash, rubric snapshot, experiment requirements, and prompt-factor snapshot, and contains an explicit prohibition on editing generated content.

- [ ] **Step 2: Run evaluator tests and verify RED**

Run: `python -m pytest backend/tests/test_assessment_evaluation.py -v`

Expected: imports fail because the evaluation service and schemas do not exist.

- [ ] **Step 3: Implement structured evaluation schemas**

```python
# backend/schemas/evaluation_schema.py
class LLMCriterionResult(BaseModel):
    criterion_key: Literal[
        "technical_correctness", "course_alignment", "blooms_alignment",
        "clarity_solution", "materials_context",
    ]
    score: int = Field(ge=1, le=5)
    justification: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    suggested_improvements: list[str] = Field(default_factory=list)
    suggested_modifications: list[str] = Field(default_factory=list)


class LLMEvaluationResponse(BaseModel):
    criteria: list[LLMCriterionResult] = Field(min_length=5, max_length=5)
    major_strengths: list[str] = Field(default_factory=list)
    major_weaknesses: list[str] = Field(default_factory=list)
    highest_priority_revision: str
    recommended_instructor_action: str

    @model_validator(mode="after")
    def require_each_criterion_once(self):
        keys = [item.criterion_key for item in self.criteria]
        if set(keys) != set(CRITERION_KEYS) or len(keys) != len(set(keys)):
            raise ValueError("each rubric criterion must appear exactly once")
        return self
```

Also define `HumanEvaluationCreate`, `HumanEvaluationPatch` with `revision`, `HumanCriterionPatch`, serialized evaluation/detail schemas, and comparison schemas.

- [ ] **Step 4: Implement evaluator configuration and service**

Add:

```python
# backend/config.py
llm_evaluation_model: Optional[str] = None
local_reviewer_id: str = "local-reviewer"
```

Add matching commented defaults to `.env.example`. Instantiate the evaluator with `LLMClient(model=settings.llm_evaluation_model or settings.llm_model)`.

`persist_assessment_questions` serializes each question with canonical JSON (`sort_keys=True`, compact separators, UTF-8), hashes it with SHA-256, inserts only missing ordinals, and never assigns into `assessment.parsed_json`.

`evaluate_question` creates an LLM `Evaluation` before the provider call, emits the approved progress messages, calls `llm.generate(system_prompt=EVALUATION_SYSTEM_PROMPT, user_message=build_evaluation_input(run, question), model_settings={"temperature": 0}, response_schema=LLMEvaluationResponse)`, and records that result through `record_model_call(db, run=run, call_id=call_id, stage="evaluation", attempt=attempt, result=result)`. If `TruncatedResponseError` includes a result, record that result before re-raising. The service validates exact criterion coverage, stores all criterion evidence, recalculates totals through `calculate_evaluation`, records model/version/timestamp, and marks the evaluation finalized. Any validation/provider exception marks that attempt failed and re-raises a sanitized domain error.

- [ ] **Step 5: Run evaluator tests and verify GREEN**

Run: `python -m pytest backend/tests/test_assessment_evaluation.py -v`

Expected: all evaluator service tests pass.

- [ ] **Step 6: Commit the evaluation service**

```powershell
git add backend/schemas/evaluation_schema.py backend/services/assessment_evaluation.py backend/tests/test_assessment_evaluation.py backend/config.py .env.example
git commit -m "Evaluate saved assessment questions" -m "Persist stable question identities and validate structured LLM rubric feedback against the immutable saved assessment so automatic evaluation is reproducible and cannot modify generated evidence."
```

### Task 4: Asynchronous evaluation pipeline, progress, retry, and token usage

**Files:**
- Create: `backend/workers/evaluation_worker.py`
- Modify: `backend/workers/assessment_worker.py`
- Modify: `backend/celery_app.py`
- Modify: `backend/models/model_call_usage.py`
- Modify: `backend/services/usage_tracking.py`
- Modify: `backend/services/run_service.py`
- Modify: `backend/schemas/run_schema.py`
- Modify: `backend/api/runs.py`
- Modify: `backend/tests/test_worker.py`
- Create: `backend/tests/test_evaluation_worker.py`
- Modify: `backend/tests/test_usage_tracking.py`
- Modify: `backend/tests/test_run_service.py`
- Modify: `backend/tests/test_run_progress.py`

**Interfaces:**
- Produces Celery task `run_llm_evaluation_pipeline(run_id: int)`.
- Produces `retry_llm_evaluation(db, assessment_id) -> Run` and enqueues only the evaluation task.
- Run detail adds `viewer_ready_at`, `progress_message`, `evaluation_status`, and `grading_available`.

- [ ] **Step 1: Write failing pipeline isolation tests**

Add tests proving:

```python
def test_generation_commits_viewer_ready_assessment_before_evaluation_is_dispatched(test_db, generation_fixture, monkeypatch):
    db = test_db
    run_id = generation_fixture.id
    evaluation_delay = Mock()
    monkeypatch.setattr("backend.workers.assessment_worker.run_llm_evaluation_pipeline.delay", evaluation_delay)
    run_generation_pipeline.run(run_id)
    saved = db.get(Run, run_id)
    assert saved.viewer_ready_at is not None
    assert saved.status == "evaluating_quality"
    assert saved.assessment.questions
    evaluation_delay.assert_called_once_with(run_id)


def test_evaluation_failure_keeps_assessment_viewable_and_never_calls_generation(test_db, generation_fixture, monkeypatch):
    db = test_db
    run_id = generation_fixture.id
    original = deepcopy(generation_fixture.assessment.parsed_json)
    monkeypatch.setattr("backend.workers.evaluation_worker.evaluate_question", Mock(side_effect=RuntimeError("evaluation unavailable")))
    run_llm_evaluation_pipeline.run(run_id)
    saved = db.get(Run, run_id)
    assert saved.status == "evaluation_failed"
    assert saved.viewer_ready_at is not None
    assert saved.assessment.parsed_json == original


def test_evaluation_retry_only_fills_failed_or_missing_questions(test_db, generation_fixture, completed_llm_evaluation, monkeypatch):
    db = test_db
    run_id = generation_fixture.id
    assessment_id = generation_fixture.assessment.id
    original_completed_id = completed_llm_evaluation.id
    evaluation_worker = Mock()
    monkeypatch.setattr("backend.workers.evaluation_worker.run_llm_evaluation_pipeline.delay", evaluation_worker)
    retry_llm_evaluation(db, assessment_id)
    assert db.get(Evaluation, original_completed_id).status == "finalized"
    evaluation_worker.assert_called_once_with(run_id)
```

Add a usage test that records an `evaluation` result with 12 input, 8 output, and 20 total tokens after earlier generation usage, then asserts the run totals and the evaluation stage detail include both calls. Add a failed-attempt test with provider usage retained from `TruncatedResponseError.result`.

- [ ] **Step 2: Run pipeline tests and verify RED**

Run: `python -m pytest backend/tests/test_worker.py backend/tests/test_evaluation_worker.py backend/tests/test_usage_tracking.py backend/tests/test_run_service.py backend/tests/test_run_progress.py -v`

Expected: failures identify missing statuses, task, retry service, run-detail fields, and evaluation usage stage.

- [ ] **Step 3: Split generation readiness from final completion**

In `assessment_worker.py`:

```python
_set_progress(db, run, "validating_assessment", "Validating generated assessment")
generated = generate_questions(result.raw_text)
assessment.parsed_json = generated.model_dump()
run.generated_json = assessment.parsed_json
persist_assessment_questions(db, assessment)
run.viewer_ready_at = utc_now()
run.status = "evaluating_quality"
run.progress_message = "Preparing generated assessment for evaluation"
db.commit()
_publish_progress(experiment.id, run.id, condition.id, "evaluating_quality")
run_llm_evaluation_pipeline.delay(run.id)
return
```

Move DOCX creation and `complete` transition out of the generation task. Map provider/prompt/parse failures to `generation_failed`; do not set `completed_at` for viewer-ready or evaluating runs.

Update `create_run` and immutable full-run retry creation to start at `preparing_prompt`, while evaluation-only retry keeps the existing run and assessment. Update run-service tests to assert these two retry paths remain distinct.

- [ ] **Step 4: Implement the evaluation worker and usage tracking**

The evaluation worker must:

1. load the run and its immutable assessment questions;
2. skip a question when a finalized evaluation for the configured evaluator model and rubric version exists;
3. call `evaluate_question` for missing/failed questions;
4. rely on `evaluate_question` to record each provider call with `stage="evaluation"`, including truncated results that carry usage;
5. persist each requested progress message and publish a snapshot;
6. set `saving_results`, build/persist the DOCX if absent, then set `complete` and `completed_at`;
7. on any evaluator failure, set `evaluation_failed`, retain `viewer_ready_at`, and publish the sanitized failure.

Update the model-call constraint and usage serializers so `evaluation` appears naturally in stage totals. Treat `generation_failed`, `evaluation_failed`, and `complete` as terminal recording states; treat all other new statuses as in progress.

- [ ] **Step 5: Update SSE snapshots and retry behavior**

`run_detail` returns:

```python
"viewer_ready_at": run.viewer_ready_at,
"progress_message": run.progress_message,
"evaluation_status": (
    "complete" if run.status == "complete"
    else "failed" if run.status == "evaluation_failed"
    else "in_progress" if run.viewer_ready_at else "not_started"
),
"grading_available": run.status == "complete" and all_questions_have_llm_evaluations(run),
"grading_question_id": first_grading_question_id(run, settings.local_reviewer_id),
```

The assessment object also returns its database `id` and ordered `question_ids` so the Viewer can render stable grading routes without deriving identity from JSON ordinals.

Update `_TERMINAL_RUN_STATES` to `{"complete", "generation_failed", "evaluation_failed"}`. The retry endpoint changes the run back to `evaluating_quality`, clears only evaluation error fields, and enqueues `run_llm_evaluation_pipeline`.

- [ ] **Step 6: Run pipeline tests and verify GREEN**

Run: `python -m pytest backend/tests/test_worker.py backend/tests/test_evaluation_worker.py backend/tests/test_usage_tracking.py backend/tests/test_run_service.py backend/tests/test_run_progress.py -v`

Expected: all targeted tests pass and prove viewer readiness, failure isolation, evaluation-only retry, and token aggregation.

- [ ] **Step 7: Commit the asynchronous pipeline**

```powershell
git add backend/workers backend/celery_app.py backend/models/model_call_usage.py backend/services/usage_tracking.py backend/services/run_service.py backend/schemas/run_schema.py backend/api/runs.py backend/tests
git commit -m "Run rubric evaluation asynchronously" -m "Unlock the Viewer after validated question persistence while a separate evaluation worker records rubric results, progress, retries, and token usage before finalizing the run and its export artifact."
```

### Task 5: Human evaluation lifecycle and comparison APIs

**Files:**
- Create: `backend/services/evaluation_service.py`
- Create: `backend/api/evaluations.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_evaluation_service.py`
- Create: `backend/tests/test_api_evaluations.py`

**Interfaces:**
- Produces draft creation/update, finalization, reopening, access logging, grading context, evaluation listing, and comparison services.
- Registers the exact routes from the design specification.

- [ ] **Step 1: Write failing lifecycle and API tests**

Cover these behaviors with real database records:

```python
def add_five_scores(db, draft, score=4):
    for key in CRITERION_KEYS:
        draft.criteria.append(EvaluationCriterion(criterion_key=key, score=score))
    db.commit()


def test_create_draft_is_idempotent_per_reviewer_and_question(test_db, evaluated_question):
    db = test_db
    question_id = evaluated_question.id
    first = create_human_draft(db, question_id, "reviewer-a")
    second = create_human_draft(db, question_id, "reviewer-a")
    other = create_human_draft(db, question_id, "reviewer-b")
    assert first.id == second.id
    assert other.id != first.id


def test_finalize_requires_five_scores_and_recalculates_server_values(test_db, human_draft):
    draft = human_draft
    with pytest.raises(IncompleteEvaluationError):
        finalize_evaluation(db, draft.id, "reviewer-a")
    add_five_scores(test_db, draft)
    finalized = finalize_evaluation(db, draft.id, "reviewer-a")
    assert finalized.status == "finalized"
    assert finalized.finalized_at is not None
    assert finalized.weighted_score == 80.0


def test_reopen_snapshots_finalized_revision_before_unlocking(test_db, finalized_human_evaluation):
    finalized = finalized_human_evaluation
    reopened = reopen_evaluation(db, finalized.id, "reviewer-a")
    assert reopened.status == "reopened"
    assert reopened.revision == 2
    assert reopened.revisions[0].snapshot["weighted_score"] == 80.0


def test_stale_patch_returns_409_and_does_not_overwrite(client, test_db, human_draft):
    draft = human_draft
    draft.revision = 2
    test_db.commit()
    response = client.patch(f"/evaluations/{draft.id}", json={"revision": 1, "overall_comments": "stale edit"})
    assert response.status_code == 409


def test_comparison_is_unavailable_before_human_finalization(client, human_draft):
    question = human_draft.question
    assert client.get(f"/assessment-questions/{question.id}/evaluation-comparison").status_code == 409


def test_llm_access_records_first_open_before_finalization_once(client, human_draft, finalized_llm_evaluation):
    human = human_draft
    llm = finalized_llm_evaluation
    first = client.post(f"/evaluations/{human.id}/llm-access", json={"llm_evaluation_id": llm.id})
    second = client.post(f"/evaluations/{human.id}/llm-access", json={"llm_evaluation_id": llm.id})
    assert first.json()["first_opened_at"] == second.json()["first_opened_at"]
    assert first.json()["opened_before_finalization"] is True
```

API tests must also assert grading context returns adjacent question IDs in experiment order, the current reviewer’s evaluation only, completed LLM content as read-only response fields, and 409 before grading availability.

- [ ] **Step 2: Run lifecycle/API tests and verify RED**

Run: `python -m pytest backend/tests/test_evaluation_service.py backend/tests/test_api_evaluations.py -v`

Expected: imports and routes fail because the service/router do not exist.

- [ ] **Step 3: Implement lifecycle services**

Implement exact service functions:

```python
create_human_draft(db, question_id: int, reviewer_id: str) -> Evaluation
update_human_draft(db, evaluation_id: int, reviewer_id: str, payload: HumanEvaluationPatch) -> Evaluation
finalize_evaluation(db, evaluation_id: int, reviewer_id: str) -> Evaluation
reopen_evaluation(db, evaluation_id: int, reviewer_id: str) -> Evaluation
record_llm_access(db, human_evaluation_id: int, llm_evaluation_id: int, reviewer_id: str) -> EvaluationAccessEvent
build_grading_context(db, question_id: int, reviewer_id: str) -> dict
build_comparison(db, question_id: int, reviewer_id: str) -> dict
```

`update_human_draft` checks ownership, editable status, and exact revision, replaces only supplied criterion fields, increments revision, and recalculates preview totals only when all five scores exist. `finalize_evaluation` reloads with a row lock, requires exactly five valid scores, calculates on the server, and commits status/timestamps transactionally. `reopen_evaluation` writes a full serialized snapshot before clearing `finalized_at` and incrementing revision.

`build_comparison` calculates per-criterion signed and absolute differences, mean absolute difference, exact agreement rate, agreement within one point, largest disagreement, weighted-score difference, and decision difference. It labels 0 `agreement`, 1 `minor_difference`, and 2+ `significant_difference`.

- [ ] **Step 4: Implement and register API routes**

Add `backend/api/evaluations.py` with:

```text
GET  /assessments/{assessment_id}/questions
GET  /assessment-questions/{question_id}/grading-context
POST /assessments/{assessment_id}/evaluations/llm/retry
GET  /assessments/{assessment_id}/evaluations
POST /assessment-questions/{question_id}/evaluations/human
PATCH /evaluations/{evaluation_id}
POST /evaluations/{evaluation_id}/finalize
POST /evaluations/{evaluation_id}/reopen
POST /evaluations/{evaluation_id}/llm-access
GET  /assessment-questions/{question_id}/evaluation-comparison
```

Resolve reviewer identity from `settings.local_reviewer_id` in one dependency function so future authentication replaces one boundary. Serialize LLM records without mutation endpoints and return 404/409/422 errors with explicit details.

- [ ] **Step 5: Run lifecycle/API tests and verify GREEN**

Run: `python -m pytest backend/tests/test_evaluation_service.py backend/tests/test_api_evaluations.py -v`

Expected: all evaluation lifecycle and API tests pass.

- [ ] **Step 6: Commit evaluation APIs**

```powershell
git add backend/services/evaluation_service.py backend/api/evaluations.py backend/main.py backend/tests/test_evaluation_service.py backend/tests/test_api_evaluations.py
git commit -m "Add human evaluation lifecycle APIs" -m "Provide reviewer-owned drafts, optimistic updates, finalization, revision-preserving reopen, LLM access auditing, and neutral comparison metrics through assessment-question routes."
```

### Task 6: Frontend evaluation contracts, API client, and pure calculations

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/api/evaluations.ts`
- Create: `frontend/src/api/evaluations.test.ts`
- Create: `frontend/src/evaluation/rubric.ts`
- Create: `frontend/src/evaluation/rubric.test.ts`

**Interfaces:**
- Produces TypeScript `Evaluation`, `EvaluationCriterion`, `GradingContext`, `EvaluationComparison`, and new run-stage types.
- Produces `evaluationsApi` CRUD/action methods and pure `calculateDraftScores`.

- [ ] **Step 1: Write failing frontend rubric/API tests**

```typescript
// frontend/src/evaluation/rubric.test.ts
import { calculateDraftScores, criterionKeys } from './rubric'

test('mirrors backend rubric weights and critical gate', () => {
  const scores = Object.fromEntries(criterionKeys.map((key) => [key, 5]))
  scores.technical_correctness = 2
  expect(calculateDraftScores(scores)).toEqual({
    weighted_score: 82,
    critical_gate: 'FAIL',
    overall_decision: 'Not ready – critical issue',
    instructor_readiness: 'Revision required',
  })
})

test('returns null calculations until all five scores exist', () => {
  expect(calculateDraftScores({ technical_correctness: 3 })).toBeNull()
})
```

Add a client test asserting PATCH sends the revision and only supplied fields, LLM access uses POST, and retry targets `/assessments/{id}/evaluations/llm/retry`.

- [ ] **Step 2: Run frontend contract tests and verify RED**

Run: `npm test -- --run src/evaluation/rubric.test.ts src/api/evaluations.test.ts`

Workdir: `frontend`

Expected: missing modules/types cause failures.

- [ ] **Step 3: Add frontend types and API methods**

Change `Stage` to the new persisted values and extend `Run` with:

```typescript
viewer_ready_at?: string | null
progress_message?: string | null
evaluation_status?: 'not_started' | 'in_progress' | 'complete' | 'failed'
grading_available?: boolean
grading_question_id?: number | null
```

Add `id` and `question_ids` to `AssessmentOutput`, add metadata to `Question` including `metadata.question_title`, and define evaluation DTOs matching backend serialization exactly.

Extend `api` with:

```typescript
patch: <T>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
```

Create `evaluationsApi` methods for grading context, create/update/finalize/reopen, access logging, comparison, and evaluation retry.

- [ ] **Step 4: Implement the mirrored pure calculator**

```typescript
export const criterionKeys = [
  'technical_correctness', 'course_alignment', 'blooms_alignment',
  'clarity_solution', 'materials_context',
] as const

const weights = { technical_correctness: 30, course_alignment: 25, blooms_alignment: 10, clarity_solution: 25, materials_context: 10 }

export function calculateDraftScores(scores: Partial<Record<CriterionKey, number>>) {
  if (!criterionKeys.every((key) => Number.isInteger(scores[key]) && scores[key]! >= 1 && scores[key]! <= 5)) return null
  const weighted_score = criterionKeys.reduce((total, key) => total + scores[key]! * weights[key] / 5, 0)
  const critical_gate = scores.technical_correctness! < 3 ? 'FAIL' : 'PASS'
  const overall_decision = critical_gate === 'FAIL' ? 'Not ready – critical issue'
    : weighted_score >= 90 ? 'Instructor-ready'
    : weighted_score >= 80 ? 'Strong – minor revision'
    : weighted_score >= 70 ? 'Usable – moderate revision'
    : weighted_score >= 60 ? 'Substantial revision' : 'Not ready'
  return { weighted_score, critical_gate, overall_decision, instructor_readiness: overall_decision === 'Instructor-ready' ? 'Instructor-ready' : 'Revision required' }
}
```

- [ ] **Step 5: Run frontend contract tests and verify GREEN**

Run: `npm test -- --run src/evaluation/rubric.test.ts src/api/evaluations.test.ts`

Workdir: `frontend`

Expected: all tests pass.

- [ ] **Step 6: Commit frontend contracts**

```powershell
git add frontend/src/types/index.ts frontend/src/api frontend/src/evaluation
git commit -m "Add frontend evaluation contracts" -m "Mirror the authoritative rubric calculations and expose typed evaluation APIs so grading components can autosave, finalize, audit LLM access, and compare results without duplicating transport details."
```

### Task 7: Progress and Viewer live evaluation experience

**Files:**
- Modify: `frontend/src/pages/ProgressPage.tsx`
- Modify: `frontend/src/pages/AssessmentViewerPage.tsx`
- Modify: `frontend/src/hooks/useSSE.ts`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Progress renders the six-stage timeline and enables Viewer access at `viewer_ready_at`.
- Viewer subscribes to run snapshots, live-updates tokens/status, and routes Grade Assessment to the first ungraded question.

- [ ] **Step 1: Write failing Progress/Viewer tests**

Add Testing Library tests that assert:

```typescript
expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
  expect.stringContaining('Preparing Prompt'),
  expect.stringContaining('Generating Assessment'),
  expect.stringContaining('Validating Assessment'),
  expect.stringContaining('Evaluating Assessment Quality'),
  expect.stringContaining('Saving Results'),
  expect.stringContaining('Complete'),
])
expect(screen.getByText('Evaluating clarity and solution quality')).toBeVisible()
expect(screen.getByRole('link', { name: 'View Assessment' })).toHaveAttribute('href', '/experiments/1/viewer/8')
```

For the Viewer, mock an initial evaluating snapshot with generation usage followed by an SSE snapshot with evaluation usage and assert:

```typescript
expect(screen.getByRole('status', { name: 'Evaluation status' })).toHaveTextContent('Evaluation in progress')
expect(screen.getByRole('button', { name: 'Evaluation in progress' })).toBeDisabled()
expect(screen.getByText('42')).toBeVisible()
// dispatch completed snapshot
expect(screen.getByRole('link', { name: 'Grade Assessment' })).toHaveAttribute('href', '/assessments/5/questions/11/grade')
expect(screen.getByText('67')).toBeVisible()
```

Also test evaluation failure retains Viewer access and exposes only the evaluation retry action, not run regeneration.

- [ ] **Step 2: Run UI tests and verify RED**

Run: `npm test -- --run src/App.test.tsx`

Workdir: `frontend`

Expected: stage, Viewer-ready, live-token, and Grade Assessment assertions fail.

- [ ] **Step 3: Implement six-stage Progress presentation**

Replace the single status card with an ordered accessible list driven by the new `Stage` order. Mark completed, current, pending, and failed states with text and classes. Render `run.progress_message` below the active stage. Show **View Assessment** whenever `viewer_ready_at` is present. On evaluation failure, add **Retry LLM Evaluation** calling the new API and preserve Viewer access.

- [ ] **Step 4: Implement live Viewer state and action placement**

Call `useSSE(selectedId, applyRunSnapshot)` in the Viewer with a stable callback. Update `useSSE` terminal states to `complete`, `generation_failed`, and `evaluation_failed`.

Replace the Viewer’s `complete` run filter with a `viewer_ready_at` filter so validated assessments appear during evaluation and after an evaluation failure. Keep runs without `viewer_ready_at` out of the Viewer selector.

In the top-right action group render in this order:

```tsx
{selected?.grading_available && selected.grading_question_id && selected.assessment?.id ? (
  <Link className="primary" to={`/assessments/${selected.assessment.id}/questions/${selected.grading_question_id}/grade`}>Grade Assessment</Link>
) : (
  <button className="primary" disabled>{selected?.evaluation_status === 'failed' ? 'Evaluation unavailable' : 'Evaluation in progress'}</button>
)}
<button className="secondary" disabled={!selected?.artifact_available} onClick={() => runsApi.exportDocx(selectedId)}>
  {selected?.artifact_available ? 'Export Word document' : 'Preparing document'}
</button>
<button className="retry-run-button" onClick={() => setRetryDialogOpen(true)}>Retry run</button>
```

Use the question list returned on the run detail to select the first question without a finalized current-reviewer human evaluation, falling back to the first question. Render a textual evaluation status badge and retain the existing `TokenUsage`, which updates from merged snapshots.

- [ ] **Step 5: Add responsive/design-system styles**

Use existing tokens, cards, badges, buttons, spacing, focus styles, and responsive breakpoints. Ensure header actions wrap below laptop widths, disabled actions remain legible, and status is not conveyed by color alone.

- [ ] **Step 6: Run UI tests and verify GREEN**

Run: `npm test -- --run src/App.test.tsx`

Workdir: `frontend`

Expected: Progress and Viewer tests pass, including live token refresh and action placement.

- [ ] **Step 7: Commit the live Viewer workflow**

```powershell
git add frontend/src/pages/ProgressPage.tsx frontend/src/pages/AssessmentViewerPage.tsx frontend/src/hooks/useSSE.ts frontend/src/App.test.tsx frontend/src/index.css
git commit -m "Expose assessments while evaluation runs" -m "Show persisted pipeline stages, unlock the Viewer after validation, stream evaluation status and token usage into the Viewer, and enable the primary grading action only when saved LLM results are ready."
```

### Task 8: Human-first Assessment Grading Page

**Files:**
- Create: `frontend/src/pages/AssessmentGradingPage.tsx`
- Create: `frontend/src/pages/AssessmentGradingPage.test.tsx`
- Create: `frontend/src/components/evaluation/Accordion.tsx`
- Create: `frontend/src/components/evaluation/RubricCriterionCard.tsx`
- Create: `frontend/src/components/evaluation/HumanEvaluationSummary.tsx`
- Create: `frontend/src/components/evaluation/LLMEvaluationPanel.tsx`
- Create: `frontend/src/components/evaluation/EvaluationComparisonPanel.tsx`
- Create: `frontend/src/hooks/useHumanEvaluationDraft.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Registers `/assessments/:assessmentId/questions/:questionId/grade`.
- Provides autosaved human draft editing, finalization/reopen, audited LLM disclosure, and post-finalization comparison.

- [ ] **Step 1: Write failing grading-page behavior tests**

Use mocked grading-context responses to assert:

```typescript
expect(screen.queryByRole('heading', { name: 'Assessment Summary' })).not.toBeInTheDocument()
const controls = screen.getAllByRole('button', { name: /View LLM Assessment|Human Assessment|Compare Human and LLM Results/ })
expect(controls.map((item) => item.textContent)).toEqual([
  'View LLM Assessment', 'Human Assessment', 'Compare Human and LLM Results',
])
expect(screen.getByRole('button', { name: 'View LLM Assessment' })).toHaveAttribute('aria-expanded', 'false')
expect(screen.getByRole('button', { name: 'Human Assessment' })).toHaveAttribute('aria-expanded', 'true')
expect(screen.getByRole('button', { name: 'Compare Human and LLM Results' })).toBeDisabled()
expect(screen.getAllByRole('radiogroup')).toHaveLength(5)
expect(screen.getByRole('button', { name: 'Finalize Human Assessment' })).toBeDisabled()
```

Additional tests must prove:

- selecting 1–5 updates the weighted preview and values outside the scale cannot be entered;
- blur autosaves only the changed completed field with the current revision;
- periodic save flushes dirty fields;
- Reset Unsaved Changes restores the last server response;
- navigation uses a blocker/confirmation when dirty;
- opening LLM sends one first-open audit request and displays read-only content;
- all five scores enable finalization, finalization locks controls, and explicit Reopen unlocks them;
- comparison enables only after finalization and displays neutral agreement copy;
- Previous/Next and Return to Viewer use grading-context IDs;
- `axe` reports no accessibility violations.

- [ ] **Step 2: Run grading-page tests and verify RED**

Run: `npm test -- --run src/pages/AssessmentGradingPage.test.tsx src/App.test.tsx`

Workdir: `frontend`

Expected: page, route, hooks, and components are missing.

- [ ] **Step 3: Implement accessible evaluation components**

`Accordion` uses a native button with `aria-expanded`, `aria-controls`, a stable panel ID, and an optional disabled state. `RubricCriterionCard` renders the rubric title/weight/description, exact anchor guidance, a native radio group for 1–5, native checkbox issue flags, and labeled textareas with the approved placeholders.

`LLMEvaluationPanel` accepts serialized data only and has no change callbacks. `EvaluationComparisonPanel` renders the score table, metrics, difference indicators, and the statement: `Agreement does not establish that either evaluator is correct.`

- [ ] **Step 4: Implement the draft hook**

`useHumanEvaluationDraft` must:

- create/load a reviewer draft from grading context;
- keep `serverDraft`, `localDraft`, `dirtyFields`, `saving`, and `saveError` separately;
- PATCH changed completed fields on blur;
- flush dirty fields every 30 seconds;
- retain dirty fields after failure and update the stored revision after success;
- expose `saveNow`, `resetUnsaved`, `finalize`, and `reopen`;
- attach `beforeunload` while dirty and provide a confirmed navigation helper for in-app Previous/Next/Return links.

Use an `AbortController` or active flag to prevent stale question responses from replacing the newly selected question.

- [ ] **Step 5: Assemble the page in the approved order**

The header contains question title, Draft/Finalized badge, Return to Viewer, Previous Assessment, and Next Assessment. Do not render an assessment metadata summary.

Render:

```tsx
<Accordion title="View LLM Assessment" defaultExpanded={false}>
  <LLMEvaluationPanel evaluation={context.llm_evaluation} />
</Accordion>
<Accordion title="Human Assessment" defaultExpanded>
  <HumanEvaluationForm draft={draft} rubric={context.rubric} />
</Accordion>
<Accordion title="Compare Human and LLM Results" defaultExpanded={false} disabled={!isFinalized}>
  <EvaluationComparisonPanel comparison={comparison} />
</Accordion>
```

Before first LLM expansion, show `Complete the human assessment before reviewing the LLM evaluation to reduce scoring bias.` On expansion, POST the access event once per loaded human evaluation and then reveal the saved read-only data.

Below five criterion cards, render automatic calculations and reviewer fields for highest-priority issue, overall comments, and the five exact recommended-action options. Add Save Draft, Finalize Human Assessment, Reset Unsaved Changes, and Return to Assessment Viewer. Lock all original fields after finalization and replace finalize with explicit Reopen Evaluation.

- [ ] **Step 6: Add grading styles and responsive behavior**

Build on `viewer-shell`, `Card`, `Button`, `Badge`, and token variables. Keep Human Assessment visually dominant through expanded content and full-width criterion cards; keep collapsed bars compact and lower contrast. Use a two-column summary only when space permits, preserve visible focus rings, and stack actions without covering content on smaller laptop widths.

- [ ] **Step 7: Run grading-page tests and verify GREEN**

Run: `npm test -- --run src/pages/AssessmentGradingPage.test.tsx src/App.test.tsx`

Workdir: `frontend`

Expected: all grading workflow, autosave, disclosure, comparison, routing, and accessibility tests pass.

- [ ] **Step 8: Commit the grading interface**

```powershell
git add frontend/src/pages/AssessmentGradingPage.tsx frontend/src/pages/AssessmentGradingPage.test.tsx frontend/src/components/evaluation frontend/src/hooks/useHumanEvaluationDraft.ts frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/index.css
git commit -m "Build human-first assessment grading" -m "Add the rubric-driven draft and finalization workflow with collapsed audited LLM feedback, revision-safe reopening, post-finalization comparison, and sequential question navigation in the existing design system."
```

### Task 9: End-to-end lifecycle, documentation, and complete verification

**Files:**
- Modify: `backend/tests/test_end_to_end_run_lifecycle.py`
- Modify: `frontend/e2e/run-lifecycle.spec.ts`
- Modify: `README.md`
- Modify: `docs/RUN_LIFECYCLE_AND_TOKEN_ACCOUNTING.md`

**Interfaces:**
- Verifies the full contract across generation, early Viewer access, asynchronous evaluation, live token updates, grading, finalization, and comparison.

- [ ] **Step 1: Write the failing backend lifecycle test**

Extend the end-to-end test to execute generation without automatically running the queued evaluation, then assert:

```python
assert run.viewer_ready_at is not None
assert run.status == "evaluating_quality"
assert run.assessment.parsed_json == generated_snapshot
assert token_usage_detail(run)["stages"][-1]["stage"] == "assessment"
```

Run the evaluation task and assert finalized LLM evaluations exist for all questions, status becomes complete, the `evaluation` token stage and totals increase, the assessment snapshot/hash remain identical, and the grading context is available. Add a failure/retry branch proving only evaluation is repeated.

- [ ] **Step 2: Run the backend lifecycle test and verify RED**

Run: `python -m pytest backend/tests/test_end_to_end_run_lifecycle.py -v`

Expected: new viewer-ready/evaluation/grading assertions fail until all integrations are correct.

- [ ] **Step 3: Complete backend integration and verify GREEN**

Fix integration boundaries only—relationship loading, task patch points, transaction refreshes, and serialized response fields—without weakening tests or changing the approved contract.

Run: `python -m pytest backend/tests/test_end_to_end_run_lifecycle.py -v`

Expected: lifecycle test passes.

- [ ] **Step 4: Write and run the browser lifecycle test**

The Playwright test must:

1. open a persisted run at Evaluating Assessment Quality;
2. click View Assessment before evaluation completes;
3. observe Evaluation in progress and initial token total;
4. receive/poll the completed snapshot and observe the increased evaluation-inclusive token total;
5. click the top-right Grade Assessment action;
6. confirm View LLM Assessment is first and closed while Human Assessment is open;
7. fill five scores, save, finalize, and verify fields lock;
8. expand comparison and verify the neutral agreement notice;
9. navigate Next Assessment and back to Viewer.

Run: `npx playwright test e2e/run-lifecycle.spec.ts`

Workdir: `frontend`.

Expected: the new lifecycle scenario passes against the configured local services.

- [ ] **Step 5: Update documentation**

Document:

- the viewer-ready boundary after validation;
- asynchronous LLM evaluation and evaluation-only retry;
- final completion after saved LLM results and artifact creation;
- rubric version and critical gate;
- `evaluation` usage stage and live Viewer token refresh;
- grading endpoints and local reviewer identity configuration;
- compatibility behavior for legacy completed assessments.

- [ ] **Step 6: Run complete backend verification**

Run:

```powershell
python -m pytest backend/tests -v
python -m alembic check
```

Expected: all tests pass (with documented PostgreSQL skips only) and Alembic reports no new upgrade operations.

- [ ] **Step 7: Run complete frontend verification**

Run:

```powershell
Set-Location frontend
npm test -- --run
npm run lint
npm run build
Set-Location ..
```

Expected: Vitest passes, ESLint exits 0, and TypeScript/Vite production build succeeds without errors.

- [ ] **Step 8: Inspect the grading UI in the in-app browser**

Use the browser-control skill to inspect Progress, Viewer during evaluation, Viewer after completion, draft grading, finalized grading, and comparison at desktop and laptop widths. Verify no clipping, overlapping action bars, hidden focus states, inaccessible accordions, or prematurely visible LLM scores. Capture defects as failing tests before fixing them.

- [ ] **Step 9: Commit lifecycle verification and documentation**

```powershell
git add backend/tests/test_end_to_end_run_lifecycle.py frontend/e2e/run-lifecycle.spec.ts README.md docs/RUN_LIFECYCLE_AND_TOKEN_ACCOUNTING.md
git commit -m "Verify assessment grading lifecycle" -m "Cover early Viewer access, live evaluation token updates, failure-isolated retries, human finalization, and comparison end to end while documenting the new completion and research-traceability boundaries."
```

- [ ] **Step 10: Run final diff and status checks**

Run:

```powershell
git diff --check
git status --short
git log -9 --format="%h%n%s%n%b"
```

Expected: no whitespace errors, only intentional files are present, and every new commit contains an explanatory paragraph with no attribution trailer.
