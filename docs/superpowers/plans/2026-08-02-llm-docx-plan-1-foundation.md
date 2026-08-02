# Plan 1: Gemini 3.5 Model and Assessment-Version Foundation

**Goal:** Prepare the existing application for the experiment by switching every Gemini stage to Gemini 3.5 Flash-Lite, preserving original assessments as immutable versions, and adding rewrite lifecycle records without changing the current DOCX path yet.

**Depends on:** Approved design specification only.

**Unblocks:** Plans 2, 3, and 4.

**Architecture:** Keep `Run` as the experiment execution aggregate. Convert `Assessment` from one row per run to immutable, numbered versions. Add an explicit canonical assessment pointer to `Run`; never infer canonicality from the highest version. Store DOCX-authoring attempts separately so failed code and validation evidence do not contaminate an assessment version.

**TDD rule:** For every task, add the failing test first, run the focused test and observe the expected failure, add the smallest production change, rerun the focused test, then run the affected regression suite.

## Scope and non-goals

This plan includes database migration, ORM relationships, model-routing compatibility, configuration, and service-level version helpers. It does not call the second LLM, execute generated code, change the viewer, or replace `docx_exporter.py`.

## Proposed files

- Modify `backend/config.py`
- Modify `backend/services/llm_client.py`
- Modify `backend/models/run.py`
- Add `backend/models/docx_authoring.py`
- Modify `backend/models/__init__.py`
- Add `backend/migrations/versions/20260802_01_assessment_versions.py`
- Add `backend/migrations/versions/20260802_02_docx_authoring_attempts.py`
- Add `backend/services/assessment_version_service.py`
- Modify `backend/tests/test_llm_client.py`
- Add `backend/tests/test_assessment_versions.py`
- Add `backend/tests/integration/test_assessment_versions_migration.py`

## Task 1: Make Gemini 3.5 Flash-Lite the default for every current LLM stage

### 1. Write failing configuration and request-shape tests

Add tests proving:

- `Settings().llm_model == "gemini-3.5-flash-lite"`;
- Gemini 3.x requests omit legacy `temperature`, `top_p`, and `seed` unless a future provider capability explicitly enables them;
- `max_output_tokens` and structured-output schemas are still sent;
- a run-level model override still works and is preserved in `execution_config`.

Example test:

```python
def test_gemini_35_omits_legacy_sampling_fields(monkeypatch):
    client, generate = fake_google_client(monkeypatch)

    client.generate("system", "user", model_settings={"temperature": 0.7})

    config = generate.call_args.kwargs["config"]
    dumped = config.model_dump(exclude_none=True)
    assert "temperature" not in dumped
    assert "top_p" not in dumped
    assert "seed" not in dumped
    assert dumped["max_output_tokens"] == 32768
```

Run:

```powershell
pytest backend/tests/test_llm_client.py backend/tests/test_run_service.py -q
```

Expected initial result: failures showing the old `gemini-3.1-flash-lite` default and sampling fields in the request.

### 2. Add a provider capability policy

Keep model-specific request logic out of the worker:

```python
@dataclass(frozen=True)
class ModelCapabilities:
    supports_sampling_controls: bool


def capabilities_for(model: str) -> ModelCapabilities:
    if model.startswith("gemini-3"):
        return ModelCapabilities(supports_sampling_controls=False)
    return ModelCapabilities(supports_sampling_controls=True)
```

Build `GenerateContentConfig` from the capability result. Change the default model in `backend/config.py` to `gemini-3.5-flash-lite`. Retain requested sampling values in run provenance, but do not falsely report them as sent; add an `effective_provider_request` map under `execution_config` if needed.

Rerun the focused tests and then:

```powershell
pytest backend/tests/test_llm_client.py backend/tests/test_run_service.py backend/tests/test_usage_tracking.py -q
```

### 3. Commit checkpoint

```text
Switch Gemini stages to 3.5 Flash-Lite

This updates the default model and makes provider request construction aware
of Gemini 3.x sampling-field compatibility. Run provenance continues to record
requested settings while the actual request records only supported controls.
```

## Task 2: Migrate existing assessments into immutable versions

### 1. Write a failing migration test

Create a pre-migration database fixture containing a completed run, one assessment, questions, evaluations, and a document artifact. Upgrade it and assert:

- the assessment is version `1`, kind `original_generation`;
- the run points `canonical_assessment_id` at that assessment;
- question and evaluation foreign keys are unchanged;
- the original `output_hash` and `parsed_json_hash` are unchanged;
- `(run_id, version)` is unique, while `run_id` alone is no longer unique;
- the legacy document artifact points to the migrated version-1 assessment;
- legacy run status and artifact download remain intact.

Example assertions:

```python
row = connection.execute(sa.text(
    "SELECT id, run_id, version, kind FROM assessments"
)).mappings().one()
assert row["version"] == 1
assert row["kind"] == "original_generation"
assert connection.scalar(sa.text(
    "SELECT canonical_assessment_id FROM runs WHERE id=:run_id"
), {"run_id": row["run_id"]}) == row["id"]
```

Run:

```powershell
pytest backend/tests/integration/test_assessment_versions_migration.py -q
```

Expected initial result: migration revision or columns do not exist.

### 2. Add migration and ORM fields

Add to `assessments`:

```python
version: Mapped[int] = mapped_column(Integer, nullable=False)
kind: Mapped[str] = mapped_column(String, nullable=False)
source_assessment_id: Mapped[int | None] = mapped_column(
    ForeignKey("assessments.id")
)
canonicalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Use these constraints:

```python
UniqueConstraint("run_id", "version", name="uq_assessments_run_version")
CheckConstraint("version >= 1", name="ck_assessments_version_positive")
CheckConstraint(
    "kind IN ('original_generation','full_rewrite')",
    name="ck_assessments_kind",
)
```

Remove the unique constraint from `Assessment.run_id`. Add nullable `runs.canonical_assessment_id`, backfill it, add its foreign key, then make it non-null for rows that already have assessments. New pending runs may keep it null until version 1 is persisted.

Add `document_artifacts.assessment_id`, backfill it from each run's migrated version-1 assessment, and make it a unique foreign key. Keep `run_id` for efficient lookup and legacy API compatibility, with a constraint that the artifact's assessment belongs to the same run. New artifacts are always owned by the assessment version whose content they represent.

Enforce same-run ownership in PostgreSQL with composite keys rather than an application-only check: add a unique key on `assessments(id, run_id)`, reference it from `document_artifacts(assessment_id, run_id)`, and use the equivalent composite foreign key for `runs(canonical_assessment_id, id)`. Make the circular canonical foreign key deferrable during the persistence transaction. Migration tests must prove that cross-run canonical pointers and artifacts are rejected by the database.

Map relationships explicitly to avoid ambiguity from the two run/assessment foreign-key paths:

```python
assessment_versions: Mapped[list["Assessment"]] = relationship(
    foreign_keys="Assessment.run_id",
    order_by="Assessment.version",
    cascade="all, delete-orphan",
)
canonical_assessment: Mapped["Assessment | None"] = relationship(
    foreign_keys=[canonical_assessment_id],
    post_update=True,
)
```

Do not keep an ORM synonym that silently maps `run.assessment` to an arbitrary version. Update call sites deliberately in Plan 3.

Rerun the migration test plus all migration tests:

```powershell
pytest backend/tests/integration/test_assessment_versions_migration.py backend/tests/integration -q
```

### 3. Commit checkpoint

```text
Version assessments without losing legacy evidence

This migration converts existing assessments to immutable version-one records
and adds an explicit canonical pointer on each run. Questions, evaluations,
hashes, and existing artifacts remain attached to their original rows.
```

## Task 3: Add DOCX-authoring attempt persistence

### 1. Write failing model tests

Test that an attempt records:

- run and source assessment IDs;
- authoring cycle number and attempt number `1` or `2` within that cycle;
- provider/model/model version/request ID;
- prompt and grounding hashes;
- returned program text and envelope;
- sandbox image digest, execution result, validation report, and failure category;
- timestamps and token usage linkage by stage;
- a uniqueness constraint on `(run_id, cycle_number, attempt_number)`.
- an optional idempotency key on attempt 1 that is unique within the run.

Test that hostile/security failures cannot be marked repairable.

### 2. Add the model

Representative shape:

```python
class DocxAuthoringAttempt(Base):
    __tablename__ = "docx_authoring_attempts"
    __table_args__ = (
        UniqueConstraint("run_id", "cycle_number", "attempt_number"),
        CheckConstraint("cycle_number >= 1"),
        CheckConstraint("attempt_number IN (1, 2)"),
        CheckConstraint(
            "status IN ('requested','generated','executing','validating',"
            "'succeeded','failed')"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    source_assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id"), nullable=False
    )
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    grounding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    program_text: Mapped[str | None] = mapped_column(Text)
    envelope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    execution_report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    validation_report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failure_category: Mapped[str | None] = mapped_column(String)
    repairable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

Add a unique constraint on `(run_id, idempotency_key)` for non-null keys. The program is evidence, not executable state. Nothing reads and executes it except the sandbox client in Plan 3. The initial workflow creates cycle 1. An explicit rewrite-only retry after exhaustion appends cycle 2 or later; it never renumbers or overwrites prior evidence. Every cycle permits one initial program and at most one repair. Cycle reservation locks the run, calculates the next cycle number, and inserts attempt 1 with status `requested` and the idempotency key in one transaction.

Run:

```powershell
pytest backend/tests/test_assessment_versions.py backend/tests/test_model_call_usage.py -q
```

### 3. Commit checkpoint

```text
Record bounded DOCX authoring attempts

This adds durable provenance for both the initial authoring call and its one
permitted repair. Execution and validation evidence remain auditable without
creating incomplete assessment versions.
```

## Task 4: Add atomic assessment-version service operations

### 1. Write failing service tests

Cover these transactions:

1. `persist_original_version` creates version 1 and sets it canonical.
2. `persist_rewrite_and_canonicalize` creates version 2, its normalized questions, its artifact, and changes the pointer in one transaction.
3. A failure while inserting the artifact rolls back version 2 and leaves version 1 canonical.
4. A second canonicalization request is idempotent only when hashes match; otherwise it conflicts.
5. Existing evaluations remain attached to version 1 and are never relabeled as rewrite evaluations.

Example transaction boundary:

```python
def persist_rewrite_and_canonicalize(db, *, run, manifest, artifact):
    with db.begin_nested():
        rewrite = Assessment(
            run_id=run.id,
            version=2,
            kind="full_rewrite",
            source_assessment_id=run.canonical_assessment_id,
            parsed_json=manifest,
            # hashes and validation fields omitted here
        )
        db.add(rewrite)
        db.flush()
        persist_questions(db, rewrite, manifest["questions"])
        db.add(artifact.for_assessment(run_id=run.id, assessment_id=rewrite.id))
        run.canonical_assessment_id = rewrite.id
        rewrite.canonicalized_at = utc_now()
    db.commit()
    return rewrite
```

### 2. Implement the smallest service layer

The service accepts already validated data. It must not call an LLM, execute code, or validate OOXML. Hash all inputs before the transaction and store those hashes. Refuse version gaps and refuse a rewrite whose `source_assessment_id` is not version 1 of the same run.

Run:

```powershell
pytest backend/tests/test_assessment_versions.py backend/tests/test_run_service.py backend/tests/test_api_runs.py -q
```

### 3. Commit checkpoint

```text
Canonicalize validated assessment rewrites atomically

This service persists a rewritten assessment, normalized questions, and its
artifact in one transaction. Any failure leaves the immutable original as the
run's canonical recovery version.
```

## Plan 1 completion gate

Run:

```powershell
pytest backend/tests/test_llm_client.py backend/tests/test_assessment_versions.py backend/tests/test_run_service.py backend/tests/test_model_call_usage.py -q
pytest backend/tests/integration -q
```

Manual checks:

- Inspect the generated Alembic SQL for PostgreSQL before deployment.
- Upgrade a copy of production-shaped data and compare row counts and hashes.
- Confirm no worker code has started using the second LLM or sandbox yet.
- Confirm the current deterministic DOCX export still works for legacy runs.

Plan 1 is complete only when all existing assessments survive migration as version 1, canonical selection is explicit, and the existing workflow remains behaviorally unchanged except for the model switch.
