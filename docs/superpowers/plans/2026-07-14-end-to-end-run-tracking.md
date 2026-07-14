# End-to-End Run Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist and display API-reported Gemini usage for each immutable run while making progress, navigation, history, idempotent creation, and required-field validation safe for concurrent runs.

**Architecture:** Add an auditable per-call usage table plus nullable run aggregates, route every run-associated Gemini call through one accounting service, and expose persisted run snapshots through run-scoped APIs and SSE. Normalize frontend state by stable IDs, use shared navigation, and validate the same conditional field contract before any transactional creation or task enqueue.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic 2, SQLAlchemy 2, PostgreSQL, Alembic, Celery, Redis/SSE, Google Gen AI SDK 1.47, pytest, React 19, TypeScript 6, React Router, Zustand, Vitest, Testing Library, Playwright.

## Global Constraints

- Feature 4 is removed: do not add or modify attachment upload, PDF, DOCX-source, Gemini Files, object-storage, or attachment documentation behavior.
- Use only API-reported Gemini usage fields; never estimate missing token counts.
- Keep additional Gemini categories separate from input and output counts.
- Every distinct Gemini request creates exactly one call record; duplicate persistence of one response is idempotent.
- Existing runs retain null aggregate fields and display “Not recorded.”
- Navigating or unmounting closes only browser progress transport and never revokes Celery work.
- All run state, progress, result, error, and token data is keyed by stable run ID.
- Invalid submissions create no experiment, condition, run, or Celery task.
- Commit messages must contain an imperative subject and an explanatory paragraph body, with no attribution trailers.
- Preserve existing untracked `.runtime/` and `prompt/anthropic-skills/` content.

---

## File Structure

### Backend

- `backend/models/model_call_usage.py`: one auditable record per Gemini request and its reported usage.
- `backend/models/run.py`: run aggregate columns and usage relationship.
- `backend/models/experiment.py`: idempotency key for atomic experiment creation.
- `backend/models/__init__.py`: register the new model with SQLAlchemy metadata.
- `backend/migrations/versions/20260714_01_run_tracking.py`: forward-only schema migration and legacy-null preservation.
- `backend/services/usage_tracking.py`: normalize persistence, deduplicate calls/responses, and update aggregates.
- `backend/services/llm_client.py`: normalize SDK usage metadata and preserve it on truncated responses.
- `backend/services/experiment_service.py`: trim/validate and transactionally create an experiment, condition, and initial run with idempotency.
- `backend/services/run_service.py`: initialize aggregate values for newly created retry/condition runs.
- `backend/workers/assessment_worker.py`: create call IDs, record every attempt, and publish run-scoped committed progress.
- `backend/schemas/experiment_schema.py`: whitespace normalization and structured conditional validation inputs.
- `backend/schemas/run_schema.py`: token totals, stage breakdown, recent-run, and persisted-progress response types.
- `backend/api/experiments.py`: idempotent creation boundary and enqueue-only-if-created behavior.
- `backend/api/runs.py`: recent runs, detailed token data, and run-scoped SSE snapshot/reconnect.
- `backend/services/docx_exporter.py`: render token summary into new result documents.
- `backend/main.py`: structured validation exception response if implemented application-wide.

### Frontend

- `frontend/src/components/AppHeader.tsx`: shared accessible logo link.
- `frontend/src/components/TokenUsage.tsx`: partial, final, legacy, and stage token presentation.
- `frontend/src/components/RecentRuns.tsx`: minimal active/completed run reopening UI.
- `frontend/src/validation/experimentValidation.ts`: pure frontend validation contract and grouped errors.
- `frontend/src/types/index.ts`: run usage, recent-run, validation, and route types.
- `frontend/src/api/client.ts`: header support and structured validation errors.
- `frontend/src/api/experiments.ts`: idempotency key submission.
- `frontend/src/api/runs.ts`: recent/detail endpoints.
- `frontend/src/store/runStore.ts`: ID-keyed experiments/runs with non-destructive merges.
- `frontend/src/hooks/useSSE.ts`: run-scoped EventSource lifecycle.
- `frontend/src/App.tsx`: run-specific progress/viewer routes.
- `frontend/src/pages/InputPanelPage.tsx`: accessible grouped validation and recent runs.
- `frontend/src/pages/ProgressPage.tsx`: persisted run reload, partial usage, and background navigation.
- `frontend/src/pages/AssessmentViewerPage.tsx`: shared header and final/legacy token display.
- `frontend/src/components/PromptFactorFields.tsx`: field IDs, ARIA errors, and change-driven clearing.
- `frontend/src/index.css`: focus, error, recent-run, usage, and progress-action styles.
- `frontend/playwright.config.ts`: browser workflow test configuration.
- `frontend/e2e/run-lifecycle.spec.ts`: concurrent-run and invalid-submission browser workflows.

### Documentation

- `README.md`: migrations, setup, concurrent runs, reopening, and validation overview.
- `docs/RUN_LIFECYCLE_AND_TOKEN_ACCOUNTING.md`: accounting and lifecycle reference.

---

### Task 1: Add the model-call ledger and legacy-safe run aggregates

**Files:**
- Create: `backend/models/model_call_usage.py`
- Modify: `backend/models/run.py`
- Modify: `backend/models/experiment.py`
- Modify: `backend/models/__init__.py`
- Create: `backend/migrations/versions/20260714_01_run_tracking.py`
- Create: `backend/tests/test_model_call_usage.py`
- Create: `backend/tests/integration/test_run_tracking_migration.py`

**Interfaces:**
- Produces: `ModelCallUsage`, `Run.input_tokens`, `Run.output_tokens`, `Run.total_tokens`, `Run.model_call_count`, `Run.model_call_usages`, and `Experiment.idempotency_key`.
- Migration revision: `20260714_01`, down revision `20260712_01`.

- [ ] **Step 1: Write failing model tests**

```python
def test_new_run_can_distinguish_zero_usage_from_legacy_missing_usage(test_db):
    new = Run(experiment_id=1, condition_id=1, run_number=1, status="pending",
              input_tokens=0, output_tokens=0, total_tokens=0, model_call_count=0)
    assert new.input_tokens == 0
    legacy = Run(experiment_id=1, condition_id=1, run_number=2, status="complete")
    assert legacy.input_tokens is None


def test_model_call_usage_keeps_extra_categories_separate(test_db, run):
    usage = ModelCallUsage(
        call_id="call-1", run_id=run.id, stage="assessment", attempt=1,
        status="response", provider_response_id="response-1",
        input_tokens=11, output_tokens=7, total_tokens=20,
        cached_content_tokens=3, reasoning_tokens=2,
        extra_token_counts={"tool_use_prompt_token_count": 1},
    )
    test_db.add(usage); test_db.commit()
    assert usage.input_tokens == 11
    assert usage.extra_token_counts == {"tool_use_prompt_token_count": 1}
```

- [ ] **Step 2: Run model tests and verify RED**

Run: `python -m pytest backend/tests/test_model_call_usage.py -v`

Expected: collection/import failure because `ModelCallUsage` and aggregate columns do not exist.

- [ ] **Step 3: Implement the SQLAlchemy model and relationships**

```python
class ModelCallUsage(Base):
    __tablename__ = "model_call_usages"
    __table_args__ = (
        CheckConstraint("stage IN ('actual_prompt','planning','validation','assessment','repair','structured_output_retry')"),
        CheckConstraint("status IN ('response','response_without_usage','failed')"),
        UniqueConstraint("call_id", name="uq_model_call_usages_call_id"),
        Index("ix_model_call_usages_run_stage", "run_id", "stage"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[str] = mapped_column(String(36), nullable=False)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    provider_response_id: Mapped[Optional[str]] = mapped_column(String)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cached_content_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    reasoning_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    extra_token_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    run: Mapped["Run"] = relationship(back_populates="model_call_usages")
```

Add nullable integer aggregates and `model_call_usages` with `cascade="all, delete-orphan"` to `Run`. Add nullable, unique, indexed `idempotency_key: String(64)` to `Experiment`. Import `ModelCallUsage` from `backend/models/__init__.py`.

- [ ] **Step 4: Run model tests and verify GREEN**

Run: `python -m pytest backend/tests/test_model_call_usage.py backend/tests/test_run_models.py backend/tests/test_experiment_models.py -v`

Expected: all selected tests pass.

- [ ] **Step 5: Write the failing migration test**

```python
def test_run_tracking_migration_preserves_legacy_usage_as_null(postgres_connection):
    upgrade_to("20260712_01")
    legacy_run_id = insert_complete_legacy_run(postgres_connection)
    upgrade_to("20260714_01")
    row = postgres_connection.execute(sa.text(
        "SELECT input_tokens, output_tokens, total_tokens, model_call_count FROM runs WHERE id=:id"
    ), {"id": legacy_run_id}).mappings().one()
    assert dict(row) == {
        "input_tokens": None, "output_tokens": None,
        "total_tokens": None, "model_call_count": None,
    }
```

- [ ] **Step 6: Run migration test and verify RED**

Run: `python -m pytest backend/tests/integration/test_run_tracking_migration.py -v`

Expected: fail because revision `20260714_01` does not exist, or skip only when `TEST_POSTGRES_DATABASE_URL` is not configured.

- [ ] **Step 7: Implement the Alembic migration**

Create the table and columns matching the ORM. Add nonnegative checks for every token/count field, the run/stage index, `ix_experiments_idempotency_key`, and a PostgreSQL partial unique index:

```python
op.create_index(
    "uq_model_call_usages_provider_response_id",
    "model_call_usages",
    ["provider_response_id"],
    unique=True,
    postgresql_where=sa.text("provider_response_id IS NOT NULL"),
)
```

Do not backfill aggregate columns. `downgrade()` drops only objects introduced by this revision in reverse dependency order.

- [ ] **Step 8: Verify migration and metadata**

Run: `python -m pytest backend/tests/integration/test_run_tracking_migration.py backend/tests/test_two_stage_migration.py -v`

Run: `python -m alembic check`

Expected: tests pass or PostgreSQL-only tests explicitly skip; Alembic reports no new upgrade operations.

- [ ] **Step 9: Commit Task 1**

```powershell
git add backend/models backend/migrations/versions/20260714_01_run_tracking.py backend/tests/test_model_call_usage.py backend/tests/integration/test_run_tracking_migration.py
git commit -m "Add model call usage persistence" -m "Create an auditable per-call Gemini usage ledger and nullable run aggregates so new runs can track exact API metadata while legacy runs remain distinguishable as not recorded."
```

---

### Task 2: Parse Gemini usage metadata and persist calls idempotently

**Files:**
- Modify: `backend/services/llm_client.py`
- Create: `backend/services/usage_tracking.py`
- Modify: `backend/tests/test_llm_client.py`
- Create: `backend/tests/test_usage_tracking.py`

**Interfaces:**
- Produces: `TokenUsage`, `LLMResult.usage`, `TruncatedResponseError.result`, and `record_model_call(db, *, run, call_id, stage, attempt, result=None, failed=False) -> ModelCallUsage`.
- Consumes: Task 1 models and aggregate fields.
- Test helper: add the following context manager to `test_llm_client.py` so mocked SDK responses remain active for the complete call:

```python
@contextmanager
def client_for_response(response):
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        mock_client.return_value.models.generate_content.return_value = response
        yield LLMClient()


def gemini_response(finish_reason="STOP"):
    return SimpleNamespace(
        text="result", response_id="response-1", model_version="v1",
        candidates=[SimpleNamespace(finish_reason=finish_reason)],
        usage_metadata=SimpleNamespace(
            prompt_token_count=100, candidates_token_count=40,
            total_token_count=155, cached_content_token_count=20,
            thoughts_token_count=15, tool_use_prompt_token_count=3,
        ),
    )
```

- [ ] **Step 1: Add failing SDK usage parsing tests**

```python
def test_llm_client_returns_api_reported_usage_without_combining_categories():
    response = gemini_response()
    with client_for_response(response) as client:
        result = client.generate("system", "user")
    assert result.usage == TokenUsage(
        input_tokens=100, output_tokens=40, total_tokens=155,
        cached_content_tokens=20, reasoning_tokens=15,
        extra_token_counts={"tool_use_prompt_token_count": 3},
    )


def test_truncated_response_error_preserves_usage():
    response = gemini_response("MAX_TOKENS")
    with pytest.raises(TruncatedResponseError) as raised:
        with client_for_response(response) as client:
            client.generate("system", "user")
    assert raised.value.result.usage.total_tokens == 155
```

- [ ] **Step 2: Run parsing tests and verify RED**

Run: `python -m pytest backend/tests/test_llm_client.py -k "usage or truncated" -v`

Expected: fail because `TokenUsage`, `LLMResult.usage`, and `TruncatedResponseError.result` are absent.

- [ ] **Step 3: Implement normalized usage parsing**

```python
@dataclass(frozen=True)
class TokenUsage:
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int]
    cached_content_tokens: Optional[int]
    reasoning_tokens: Optional[int]
    extra_token_counts: dict[str, int]


def _usage_from_response(response) -> Optional[TokenUsage]:
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return None
    raw = metadata.model_dump(exclude_none=True) if hasattr(metadata, "model_dump") else vars(metadata)
    known = {
        "prompt_token_count", "candidates_token_count", "total_token_count",
        "cached_content_token_count", "thoughts_token_count",
    }
    extras = {
        key: value for key, value in raw.items()
        if key.endswith("_token_count") and key not in known and isinstance(value, int)
    }
    return TokenUsage(
        input_tokens=getattr(metadata, "prompt_token_count", None),
        output_tokens=getattr(metadata, "candidates_token_count", None),
        total_tokens=getattr(metadata, "total_token_count", None),
        cached_content_tokens=getattr(metadata, "cached_content_token_count", None),
        reasoning_tokens=getattr(metadata, "thoughts_token_count", None),
        extra_token_counts=extras,
    )
```

Construct `LLMResult` before finish-reason validation. Raise `TruncatedResponseError(result)` with a safe message and a public `result` property. Update existing result equality tests to include `usage=None`.

- [ ] **Step 4: Run all LLM tests and verify GREEN**

Run: `python -m pytest backend/tests/test_llm_client.py -v`

Expected: all tests pass.

- [ ] **Step 5: Write failing accounting tests**

Define this concrete result factory in `test_usage_tracking.py`:

```python
def result(response_id, input_tokens, output_tokens, total_tokens):
    return LLMResult(
        raw_text="result", provider_request_id=response_id,
        model_name="gemini", model_version="v1", finish_reason="STOP",
        usage=TokenUsage(input_tokens, output_tokens, total_tokens, None, None, {}),
    )
```

```python
def test_record_model_call_aggregates_two_responses_once(test_db, run):
    record_model_call(test_db, run=run, call_id="a", stage="actual_prompt", attempt=1,
                      result=result("r1", 10, 4, 14))
    record_model_call(test_db, run=run, call_id="b", stage="assessment", attempt=1,
                      result=result("r2", 20, 8, 28))
    record_model_call(test_db, run=run, call_id="b", stage="assessment", attempt=1,
                      result=result("r2", 20, 8, 28))
    test_db.refresh(run)
    assert (run.input_tokens, run.output_tokens, run.total_tokens, run.model_call_count) == (30, 12, 42, 2)


def test_failed_call_counts_request_without_inventing_tokens(test_db, run):
    usage = record_model_call(test_db, run=run, call_id="failed", stage="assessment",
                              attempt=2, failed=True)
    assert usage.status == "failed"
    assert usage.total_tokens is None
    assert run.model_call_count == 1
```

- [ ] **Step 6: Run accounting tests and verify RED**

Run: `python -m pytest backend/tests/test_usage_tracking.py -v`

Expected: import failure because `record_model_call` does not exist.

- [ ] **Step 7: Implement transactional accounting**

`record_model_call` checks `call_id` first and provider response ID second. If found, return the existing row without changing aggregates. Otherwise insert one row, increment `model_call_count`, add only non-null API-reported categories to the corresponding aggregate, and commit. Use `with db.begin_nested()` plus `IntegrityError` recovery so concurrent duplicate persistence returns the winner.

Status is `failed` when no result exists, `response_without_usage` when `result.usage is None`, and `response` otherwise. Never derive `total_tokens` from input plus output.

- [ ] **Step 8: Run accounting and regression tests**

Run: `python -m pytest backend/tests/test_usage_tracking.py backend/tests/test_llm_client.py backend/tests/test_run_models.py -v`

Expected: all tests pass.

- [ ] **Step 9: Commit Task 2**

```powershell
git add backend/services/llm_client.py backend/services/usage_tracking.py backend/tests/test_llm_client.py backend/tests/test_usage_tracking.py
git commit -m "Record API-reported Gemini usage" -m "Normalize Gemini SDK usage metadata and persist every distinct request idempotently, including truncated responses and failures without fabricated token values."
```

---

### Task 3: Integrate accounting and run-scoped progress into the Celery pipeline

**Files:**
- Modify: `backend/workers/assessment_worker.py`
- Modify: `backend/services/run_service.py`
- Modify: `backend/tests/test_worker.py`
- Modify: `backend/tests/test_research_run_workflow.py`

**Interfaces:**
- Consumes: `record_model_call` and `TruncatedResponseError.result` from Task 2.
- Produces: committed `run:{run_id}:progress` messages containing a complete safe snapshot discriminator.
- Test helpers: add this result factory and synchronous runner to `test_worker.py`:

```python
def result(raw_text, input_tokens, output_tokens, total_tokens, finish="STOP"):
    return LLMResult(
        raw_text=raw_text, provider_request_id=f"response-{total_tokens}",
        model_name="gemini", model_version="v1", finish_reason=finish,
        usage=TokenUsage(input_tokens, output_tokens, total_tokens, None, None, {}),
    )


def run_pipeline_synchronously(run, test_db, llm):
    with (
        patch("backend.workers.assessment_worker.LLMClient", return_value=llm),
        patch("backend.workers.assessment_worker.SessionLocal", return_value=test_db),
        patch("backend.workers.assessment_worker.redis_client"),
    ):
        test_db.close = MagicMock()
        run_generation_pipeline.run(run.id)
```

- [ ] **Step 1: Write failing worker accounting and retry tests**

```python
def test_pipeline_records_both_stage_usage(generation_fixture, test_db):
    llm.generate.side_effect = [result("structure", 10, 5, 15), result("assessment", 20, 8, 28)]
    run_pipeline_synchronously(generation_fixture, test_db, llm)
    calls = test_db.query(ModelCallUsage).filter_by(run_id=generation_fixture.id).all()
    assert [(call.stage, call.total_tokens) for call in calls] == [
        ("actual_prompt", 15), ("assessment", 28),
    ]
    assert generation_fixture.total_tokens == 43


def test_truncated_retry_records_response_usage_once(generation_fixture, test_db):
    truncated = TruncatedResponseError(result("truncated", 20, 1, 30, finish="MAX_TOKENS"))
    llm.generate.side_effect = [result("structure", 10, 5, 15), truncated]
    with pytest.raises(Retry):
        run_pipeline_synchronously(generation_fixture, test_db, llm)
    assert test_db.query(ModelCallUsage).filter_by(run_id=generation_fixture.id).count() == 2
    assert generation_fixture.total_tokens == 45
```

Also assert Redis publishes `run:{id}:progress`, and that rerunning a task with a persisted prompt does not create another `actual_prompt` call.

- [ ] **Step 2: Run worker tests and verify RED**

Run: `python -m pytest backend/tests/test_worker.py -k "usage or progress or retry" -v`

Expected: assertions fail because the worker does not persist usage or publish run channels.

- [ ] **Step 3: Implement a single run-aware call helper in the worker**

```python
def _call_gemini(task, db, run, llm, *, stage, system_prompt, user_message,
                 model_settings, response_schema=None):
    call_id = str(uuid.uuid4())
    attempt = sum(1 for item in run.model_call_usages if item.stage == stage) + 1
    try:
        result = llm.generate(system_prompt, user_message, model_settings, response_schema)
    except TruncatedResponseError as exc:
        record_model_call(db, run=run, call_id=call_id, stage=stage,
                          attempt=attempt, result=exc.result)
        raise
    except Exception:
        record_model_call(db, run=run, call_id=call_id, stage=stage,
                          attempt=attempt, failed=True)
        raise
    record_model_call(db, run=run, call_id=call_id, stage=stage,
                      attempt=attempt, result=result)
    return result
```

Use it for both current Gemini calls. Keep stage outputs committed before retries. Initialize aggregate fields to zero in `create_run` and retry-created runs.

- [ ] **Step 4: Publish committed run-scoped progress**

Change `_publish_progress` to publish the existing compatibility message to `experiment:{experiment_id}:progress` and the same safe message to `run:{run_id}:progress`. Call it only after `_set_status` or error state commits.

- [ ] **Step 5: Run worker and workflow tests**

Run: `python -m pytest backend/tests/test_worker.py backend/tests/test_research_run_workflow.py backend/tests/test_run_service.py -v`

Expected: all tests pass, including existing two-stage provenance assertions.

- [ ] **Step 6: Commit Task 3**

```powershell
git add backend/workers/assessment_worker.py backend/services/run_service.py backend/tests/test_worker.py backend/tests/test_research_run_workflow.py
git commit -m "Track usage across generation stages" -m "Route both Gemini stages and their Celery retries through run-aware accounting, while publishing committed progress on isolated run channels without changing page-unmount behavior."
```

---

### Task 4: Make experiment creation validated, transactional, and idempotent

**Files:**
- Create: `backend/services/experiment_service.py`
- Modify: `backend/schemas/experiment_schema.py`
- Modify: `backend/api/experiments.py`
- Modify: `backend/main.py`
- Modify: `backend/tests/test_experiment_schemas.py`
- Modify: `backend/tests/test_api_experiments.py`
- Create: `backend/tests/test_experiment_service.py`

**Interfaces:**
- Produces: `ValidationIssue(section, field, label, message)`, `ExperimentValidationError`, and `create_experiment_with_run(db, payload, idempotency_key) -> tuple[Experiment, Run, bool]`.
- API: `POST /experiments` requires `Idempotency-Key` and returns the existing response shape plus the initial run.
- Test factories: retain the existing complete request factory in `test_api_experiments.py` as `valid_payload()` and define `incomplete_payload()` as `{**valid_payload(), "course": "", "topic": "", "learning_objectives": ""}`.

- [ ] **Step 1: Write failing whitespace and conditional validation tests**

```python
@pytest.mark.parametrize("field", ["course", "topic", "learning_objectives"])
def test_assessment_text_fields_reject_whitespace(field, valid_payload):
    valid_payload[field] = "   "
    with pytest.raises(ValidationError):
        ExperimentCreate(**valid_payload)


def test_enabled_reference_content_requires_trimmed_text(valid_payload):
    valid_payload["factors"]["reference_content"] = True
    valid_payload["factor_inputs"]["reference_content"] = "  "
    with pytest.raises(ValidationError):
        ExperimentCreate(**valid_payload)
```

- [ ] **Step 2: Run schema tests and verify RED**

Run: `python -m pytest backend/tests/test_experiment_schemas.py -v`

Expected: whitespace-only always-required fields currently pass field-level constraints or return an unstructured root error.

- [ ] **Step 3: Normalize and validate schema values**

Use `field_validator(..., mode="before")` to strip assessment text and optional factor text. Keep the after-validator for enabled factors, but raise errors through a service-owned structured issue list at the API boundary so user-facing labels are stable.

- [ ] **Step 4: Write failing transaction and idempotency tests**

```python
def test_duplicate_idempotency_key_returns_one_run_and_enqueues_once(client):
    with patch("backend.api.experiments.run_generation_pipeline.delay") as delay:
        first = client.post("/experiments", headers={"Idempotency-Key": "submission-1"}, json=valid_payload())
        second = client.post("/experiments", headers={"Idempotency-Key": "submission-1"}, json=valid_payload())
    assert first.status_code == second.status_code == 200
    assert first.json()["runs"][0]["id"] == second.json()["runs"][0]["id"]
    delay.assert_called_once()


def test_invalid_request_creates_nothing_and_enqueues_nothing(client, test_db):
    with patch("backend.api.experiments.run_generation_pipeline.delay") as delay:
        response = client.post("/experiments", headers={"Idempotency-Key": "invalid"}, json=incomplete_payload())
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0].keys() == {"section", "field", "label", "message"}
    assert test_db.query(Experiment).count() == 0
    assert test_db.query(Run).count() == 0
    delay.assert_not_called()
```

- [ ] **Step 5: Run API/service tests and verify RED**

Run: `python -m pytest backend/tests/test_experiment_service.py backend/tests/test_api_experiments.py -v`

Expected: fail because idempotent transactional creation and structured errors do not exist.

- [ ] **Step 6: Implement the creation service**

Within one transaction, query `Experiment.idempotency_key`; return `(experiment, experiment.runs[0], False)` if it exists. Otherwise create experiment, condition, and a run initialized with zero aggregates, flush them, and commit once. On `IntegrityError`, roll back and retrieve the row that won the uniqueness race. Never enqueue from the service.

Require a nonblank `Idempotency-Key` header of at most 64 characters. The API calls `delay(run.id)` only when `created is True`.

- [ ] **Step 7: Return structured validation errors safely**

Install a FastAPI `RequestValidationError` handler that maps known experiment request paths to Assessment Details or Prompt Design Factors and their user-facing labels. Preserve standard 422 behavior for unrelated endpoints. Do not include raw exception traces or internal column names.

- [ ] **Step 8: Run transactional validation tests**

Run: `python -m pytest backend/tests/test_experiment_schemas.py backend/tests/test_experiment_service.py backend/tests/test_api_experiments.py backend/tests/test_main.py -v`

Expected: all tests pass; invalid and duplicate submissions enqueue zero and one tasks respectively.

- [ ] **Step 9: Commit Task 4**

```powershell
git add backend/services/experiment_service.py backend/schemas/experiment_schema.py backend/api/experiments.py backend/main.py backend/tests/test_experiment_schemas.py backend/tests/test_experiment_service.py backend/tests/test_api_experiments.py backend/tests/test_main.py
git commit -m "Make run creation idempotent" -m "Validate trimmed assessment inputs before mutation and create each experiment, condition, and initial run in one transaction so duplicate submissions reuse one run and invalid requests enqueue no work."
```

---

### Task 5: Expose token totals, recent runs, persisted SSE snapshots, and exports

**Files:**
- Modify: `backend/schemas/run_schema.py`
- Modify: `backend/schemas/experiment_schema.py`
- Modify: `backend/api/runs.py`
- Modify: `backend/services/docx_exporter.py`
- Modify: `backend/workers/assessment_worker.py`
- Modify: `backend/tests/test_api_runs.py`
- Modify: `backend/tests/test_docx_exporter.py`
- Create: `backend/tests/test_run_progress.py`

**Interfaces:**
- Produces: `TokenTotals`, `StageUsage`, `RunDetail`, `RecentRun`, `GET /runs/recent`, and `GET /runs/{run_id}/progress`.
- Route ordering constraint: declare `/runs/recent` before `/runs/{run_id}`.

- [ ] **Step 1: Write failing run-detail and recent-run tests**

```python
def test_run_detail_exposes_totals_and_stage_breakdown(client, run_with_usage):
    body = client.get(f"/runs/{run_with_usage.id}").json()
    assert body["token_usage"] == {
        "input_tokens": 30, "output_tokens": 12, "total_tokens": 42,
        "model_calls": 2, "recording_state": "recorded",
        "stages": [
            {"stage": "actual_prompt", "input_tokens": 10, "output_tokens": 4,
             "total_tokens": 14, "model_calls": 1},
            {"stage": "assessment", "input_tokens": 20, "output_tokens": 8,
             "total_tokens": 28, "model_calls": 1},
        ],
    }


def test_recent_runs_returns_active_and_completed_in_reverse_order(client, runs):
    body = client.get("/runs/recent?limit=10").json()
    assert [item["id"] for item in body] == [runs.newest.id, runs.oldest.id]
```

Legacy null totals must serialize with `recording_state="not_recorded"`; active runs use `recording_state="in_progress"`.

- [ ] **Step 2: Run API tests and verify RED**

Run: `python -m pytest backend/tests/test_api_runs.py -k "token or recent" -v`

Expected: missing token fields and `/runs/recent` route.

- [ ] **Step 3: Implement schema serialization and stage aggregation**

Add a pure `token_usage_detail(run)` helper. Sum only non-null fields per stage, count every call row, and set recording state from aggregate nullability plus terminal status. Include cached/reasoning values in stage details only when available; never add them into input/output.

Recent rows include run ID, experiment ID, condition ID, run number, status, topic, condition label, created time, completed time, and token summary. Bound `limit` from 1 through 50.

- [ ] **Step 4: Write failing persisted-progress tests**

```python
@pytest.mark.asyncio
async def test_progress_stream_emits_database_snapshot_before_redis(run):
    event = await first_event(_stream_run_progress(run.id, session_factory, redis_factory))
    assert json.loads(event["data"])["status"] == run.status
    assert json.loads(event["data"])["run_id"] == run.id


@pytest.mark.asyncio
async def test_terminal_snapshot_closes_without_waiting_for_redis(complete_run):
    events = [event async for event in _stream_run_progress(complete_run.id, session_factory, redis_factory)]
    assert len(events) == 1
    assert json.loads(events[0]["data"])["status"] == "complete"
```

- [ ] **Step 5: Run progress tests and verify RED**

Run: `python -m pytest backend/tests/test_run_progress.py -v`

Expected: import failure because `_stream_run_progress` is absent.

- [ ] **Step 6: Implement run-scoped SSE**

Read the run in a short-lived database session, emit `run_detail` as the first SSE data event, and return immediately if terminal. Otherwise subscribe to `run:{run_id}:progress`; for each Redis signal, re-read persisted run state and emit it. Close after terminal state. Always unsubscribe and close Redis in `finally`. A disconnected browser performs no state mutation.

- [ ] **Step 7: Put token totals into generated Word artifacts**

Extend `build_assessment_docx(..., token_usage: Optional[dict] = None)`. Add an “End-to-end token usage” metadata block containing Input, Output, Total, and Model calls, or “Not recorded.” Pass the run summary from the worker after both model calls have been recorded.

- [ ] **Step 8: Run API, SSE, export, and worker tests**

Run: `python -m pytest backend/tests/test_api_runs.py backend/tests/test_run_progress.py backend/tests/test_docx_exporter.py backend/tests/test_worker.py -v`

Expected: all tests pass.

- [ ] **Step 9: Commit Task 5**

```powershell
git add backend/schemas/run_schema.py backend/schemas/experiment_schema.py backend/api/runs.py backend/services/docx_exporter.py backend/workers/assessment_worker.py backend/tests/test_api_runs.py backend/tests/test_run_progress.py backend/tests/test_docx_exporter.py backend/tests/test_worker.py
git commit -m "Expose run usage and persisted progress" -m "Return token totals and stage detail through run APIs, support recent-run reopening with database-first SSE snapshots, and include accounting in generated Word evidence."
```

---

### Task 6: Normalize frontend state and add shared navigation, recent runs, and run-specific progress

**Files:**
- Create: `frontend/src/components/AppHeader.tsx`
- Create: `frontend/src/components/TokenUsage.tsx`
- Create: `frontend/src/components/RecentRuns.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/experiments.ts`
- Modify: `frontend/src/api/runs.ts`
- Modify: `frontend/src/store/runStore.ts`
- Modify: `frontend/src/store/runStore.test.ts`
- Modify: `frontend/src/hooks/useSSE.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/InputPanelPage.tsx`
- Modify: `frontend/src/pages/ProgressPage.tsx`
- Modify: `frontend/src/pages/AssessmentViewerPage.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Routes: `/runs/:runId/progress`, `/experiments/:experimentId/viewer/:runId?`, and `/`.
- Store: `experiments: Record<number, Experiment>`, `runs: Record<number, Run>`, `mergeExperiment`, `mergeRun`, and `applyRunSnapshot`.
- API: `runsApi.recent(limit)`, `runsApi.get(id)`, and `experimentsApi.create(payload, idempotencyKey)`.

- [ ] **Step 1: Write failing normalized-store tests**

```typescript
test('loading a second experiment preserves the first run', () => {
  store.mergeExperiment(first)
  store.mergeExperiment(second)
  expect(store.runs[first.runs[0].id]).toEqual(first.runs[0])
  expect(store.runs[second.runs[0].id]).toEqual(second.runs[0])
})

test('a run snapshot updates only its matching id', () => {
  store.mergeRun(runA); store.mergeRun(runB)
  store.applyRunSnapshot({ ...runA, status: 'generating' })
  expect(store.runs[runA.id].status).toBe('generating')
  expect(store.runs[runB.id].status).toBe(runB.status)
})
```

- [ ] **Step 2: Run store tests and verify RED**

Run: `cd frontend; npm test -- --run src/store/runStore.test.ts`

Expected: fail because `mergeExperiment`, experiment maps, and snapshot merge do not exist.

- [ ] **Step 3: Implement non-destructive normalized state**

Replace singleton `experiment` and reset-on-create with maps. `mergeExperiment` merges its runs and the experiment without clearing other keys. Keep `reset` only for test isolation, not submission. Route-local components select IDs from params.

- [ ] **Step 4: Write failing shared-header and recent-run tests**

```typescript
test.each(['/','/runs/8/progress','/experiments/1/viewer/8'])(
  'logo navigates client-side from %s', async (path) => {
    window.history.replaceState({}, '', path)
    render(<App />)
    const logo = await screen.findByRole('link', { name: 'Go to Blueprint Lab home' })
    expect(logo).toHaveAttribute('href', '/')
    await userEvent.click(logo)
    expect(window.location.pathname).toBe('/')
  },
)

test('recent active run reopens run-specific progress', async () => {
  render(<App />)
  await userEvent.click(await screen.findByRole('link', { name: /Reopen.*Equilibrium/ }))
  expect(window.location.pathname).toBe('/runs/8/progress')
})
```

- [ ] **Step 5: Run navigation tests and verify RED**

Run: `cd frontend; npm test -- --run src/App.test.tsx`

Expected: shared accessible link and recent-run controls are missing.

- [ ] **Step 6: Implement shared UI components**

`AppHeader` returns a `<header>` containing `<Link className="logo-link" to="/" aria-label="Go to Blueprint Lab home">Blueprint Lab</Link>` and the page subtitle. Use it on every page.

`RecentRuns` maps active statuses to `/runs/{id}/progress` and terminal complete status to `/experiments/{experiment_id}/viewer/{id}`. `TokenUsage` renders “Not recorded” when state is `not_recorded`, an “In progress” badge for active state, four labeled values, and a `<details>` stage breakdown.

- [ ] **Step 7: Implement APIs, routes, and run-scoped SSE**

Allow `api.post` to receive headers. Generate one `crypto.randomUUID()` when a submit begins and pass it as `Idempotency-Key`; reuse it only for a retry of that same pending submission. Change `useSSE(runId, onSnapshot)` to open `/api/runs/${runId}/progress`, parse full run snapshots, close on terminal state/error/unmount, and call no mutation endpoint.

Progress loads `runsApi.get(runId)` immediately, subscribes by run ID, and displays `TokenUsage`. Its bottom-right action area contains the exact supporting text and a React Router link/button to `/`. Viewer loads the route-selected run and renders the same token component inside Experiment Condition.

- [ ] **Step 8: Add accessible focus and layout styles**

Add `.logo-link:focus-visible`, `.progress-exit`, `.recent-runs`, `.token-usage`, and `.usage-state` styles. Keep the exit action inside normal content with `display:flex; justify-content:flex-end`, at least 24px top margin, and no fixed positioning.

- [ ] **Step 9: Run frontend component and accessibility tests**

Run: `cd frontend; npm test -- --run src/store/runStore.test.ts src/App.test.tsx`

Expected: all tests pass, including `jest-axe` checks.

- [ ] **Step 10: Commit Task 6**

```powershell
git add frontend/src
git commit -m "Add concurrent run navigation" -m "Normalize frontend state by stable IDs, provide shared logo navigation and recent-run reopening, and reconnect progress through persisted run-specific snapshots without cancelling backend work."
```

---

### Task 7: Add grouped accessible frontend validation with inline clearing

**Files:**
- Create: `frontend/src/validation/experimentValidation.ts`
- Modify: `frontend/src/pages/InputPanelPage.tsx`
- Modify: `frontend/src/components/PromptFactorFields.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Produces: `validateExperimentForm(values) -> ValidationError[]` where each error has `section`, `field`, `label`, and `message`.
- Field IDs are stable and shared by modal focus controls, labels, `aria-describedby`, and inline errors.

- [ ] **Step 1: Write failing pure validation tests**

Create `frontend/src/validation/experimentValidation.test.ts`:

```typescript
test('returns every missing field grouped by user-facing section', () => {
  const errors = validateExperimentForm(emptyForm)
  expect(errors.map(({ section, label }) => ({ section, label }))).toEqual([
    { section: 'Assessment Details', label: 'Course name' },
    { section: 'Assessment Details', label: 'Topic' },
    { section: 'Assessment Details', label: 'Learning objectives' },
  ])
})

test('requires only enabled factor content', () => {
  const errors = validateExperimentForm({
    ...validForm,
    enabled: { ...validForm.enabled, referenceContent: true },
    content: { ...validForm.content, referenceContent: '   ' },
  })
  expect(errors).toContainEqual(expect.objectContaining({
    section: 'Prompt Design Factors',
    label: 'Reference Content: add reference content',
  }))
})
```

- [ ] **Step 2: Run pure validation tests and verify RED**

Run: `cd frontend; npm test -- --run src/validation/experimentValidation.test.ts`

Expected: import failure because the validator does not exist.

- [ ] **Step 3: Implement the pure validator**

Use trimmed string checks, integer/range checks, and enabled-only factor checks matching backend bounds exactly. Return all errors in visual field order. Feature 4 remains absent; enabled Reference Content is satisfied only by nonblank text.

- [ ] **Step 4: Write failing modal, focus, ARIA, and clearing tests**

```typescript
test('shows a red grouped dialog and sends no request for an incomplete form', async () => {
  render(<App />)
  await user.click(screen.getByRole('button', { name: 'Run Experiment' }))
  const dialog = screen.getByRole('dialog', { name: 'Complete the required fields before running the experiment.' })
  expect(dialog).toHaveClass('validation-dialog')
  expect(within(dialog).getByRole('heading', { name: 'Assessment Details' })).toBeVisible()
  expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining('/experiments'), expect.anything())
})

test('focuses the first invalid field and clears only its error when valid', async () => {
  render(<App />)
  await user.click(screen.getByRole('button', { name: 'Run Experiment' }))
  await user.click(screen.getByRole('button', { name: 'Close' }))
  const course = screen.getByLabelText('Course name')
  expect(course).toHaveFocus()
  expect(course).toHaveAttribute('aria-invalid', 'true')
  await user.type(course, 'Statics')
  expect(course).not.toHaveAttribute('aria-invalid', 'true')
  expect(screen.getByText('Topic is required.')).toBeVisible()
})
```

- [ ] **Step 5: Run UI validation tests and verify RED**

Run: `cd frontend; npm test -- --run src/App.test.tsx -t "grouped|focuses|incomplete"`

Expected: dialog title/grouping, focus movement, and ARIA assertions fail.

- [ ] **Step 6: Implement the accessible validation experience**

Store errors by field and preserve the ordered list for the dialog. On submit, set all errors, show the dialog, and skip `experimentsApi.create`. Dialog controls change the wizard section, close the dialog, then focus the target by stable ID in `requestAnimationFrame`. Closing normally focuses the first error.

Every invalid input uses `aria-invalid="true"` and `aria-describedby="{field}-error"`; inline text uses that ID. Each change handler revalidates only its field and removes its error when valid. The dialog uses the exact approved title and separate headings for Assessment Details and Prompt Design Factors.

- [ ] **Step 7: Style error states visibly**

Add a red left/top treatment to `.validation-dialog`, red border plus focus ring to `[aria-invalid="true"]`, and visible section headings. Do not remove native outlines without a replacement.

- [ ] **Step 8: Run all frontend tests**

Run: `cd frontend; npm test -- --run`

Expected: all Vitest and accessibility tests pass.

- [ ] **Step 9: Commit Task 7**

```powershell
git add frontend/src/validation frontend/src/pages/InputPanelPage.tsx frontend/src/components/PromptFactorFields.tsx frontend/src/App.test.tsx frontend/src/index.css
git commit -m "Improve required-field validation" -m "Report every missing assessment and enabled-factor field in a red grouped dialog with inline ARIA feedback, focus recovery, and change-driven error clearing before any backend request."
```

---

### Task 8: Add end-to-end workflows, documentation, and full verification

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/run-lifecycle.spec.ts`
- Create: `backend/tests/test_end_to_end_run_lifecycle.py`
- Modify: `README.md`
- Create: `docs/RUN_LIFECYCLE_AND_TOKEN_ACCOUNTING.md`
- Modify: `.env.example` only if implementation introduced an actual non-secret setting.

**Interfaces:**
- Browser command: `cd frontend; npx playwright test`.
- Backend workflow command: `python -m pytest backend/tests/test_end_to_end_run_lifecycle.py -v`.
- Backend test helpers: `create_valid_experiment(client, key)` posts the existing valid payload with that idempotency key and returns a namespace containing the first response run ID; `run_worker_with_mocked_gemini(run_id, usage)` builds two valid `LLMResult` instances from the supplied `(input, output, total)` tuples, patches `SessionLocal`, `LLMClient`, Redis, and DOCX generation exactly as `test_worker.py` does, then calls `run_generation_pipeline.run(run_id)`.

- [ ] **Step 1: Write the failing backend end-to-end workflow**

```python
def test_two_runs_finish_independently_and_reopen_with_isolated_tokens(client, test_db):
    first = create_valid_experiment(client, key="first")
    second = create_valid_experiment(client, key="second")
    run_worker_with_mocked_gemini(first.run_id, usage=[(10, 4, 14), (20, 8, 28)])
    run_worker_with_mocked_gemini(second.run_id, usage=[(100, 40, 140), (200, 80, 280)])
    reopened = client.get(f"/runs/{first.run_id}").json()
    assert reopened["status"] == "complete"
    assert reopened["token_usage"]["total_tokens"] == 42
    assert client.get(f"/runs/{second.run_id}").json()["token_usage"]["total_tokens"] == 420


def test_incomplete_submission_creates_no_research_rows_or_task(client, test_db):
    with patch("backend.api.experiments.run_generation_pipeline.delay") as delay:
        response = client.post("/experiments", headers={"Idempotency-Key": "bad"}, json={})
    assert response.status_code == 422
    assert test_db.query(Experiment).count() == 0
    assert test_db.query(Run).count() == 0
    delay.assert_not_called()
```

- [ ] **Step 2: Run the backend acceptance workflow**

Run: `python -m pytest backend/tests/test_end_to_end_run_lifecycle.py -v`

Expected: pass after Tasks 1–7. A failure identifies a regression in the already-specified interfaces; fix that interface under its owning task and retain the acceptance assertions unchanged.

- [ ] **Step 3: Verify the complete backend suite after the workflow**

Run: `python -m pytest backend/tests -v`

Expected: all unit and workflow tests pass; PostgreSQL-only tests may report only their documented explicit skip when `TEST_POSTGRES_DATABASE_URL` is absent.

- [ ] **Step 4: Add Playwright and write failing browser workflows**

Install `@playwright/test` as a dev dependency. Configure `webServer.command` as `npm run dev -- --host 127.0.0.1` and `baseURL` as `http://127.0.0.1:5173`.

The first browser test fulfills a valid form, starts run 1 through mocked API responses, uses Back to Control Assessment, starts run 2, verifies both appear in Recent runs, reopens run 1, and verifies its status and token total remain isolated. The second submits an empty form, verifies the red grouped dialog and all missing labels, and asserts the intercepted experiment POST count remains zero.

- [ ] **Step 5: Run Playwright workflows**

Run: `cd frontend; npx playwright install chromium`

Run: `cd frontend; npx playwright test`

Expected: both workflows pass. If browser installation is unavailable in the execution environment, record the exact failure and still run all Vitest integration coverage; do not claim Playwright passed.

- [ ] **Step 6: Write the lifecycle/accounting documentation**

`docs/RUN_LIFECYCLE_AND_TOKEN_ACCOUNTING.md` must define:

- Input = Gemini `prompt_token_count`.
- Output = Gemini `candidates_token_count`.
- Total = Gemini `total_token_count`, not recomputed.
- Cached and thoughts/reasoning categories remain separate.
- Every actual-prompt, assessment, retry, repair, validation, or future run-associated Gemini request counts as a model call.
- Responses with usage count even when later rejected; failures without usage contain null tokens.
- Aggregates sum only distinct call records for one run.
- Legacy null aggregates display “Not recorded.”
- Run IDs isolate Celery work, Redis channels, results, errors, and usage.
- Leaving progress closes only SSE; recent runs reopen persisted state.
- Idempotency and required-field rules.
- Feature 4 and attachment/PDF behavior are not part of this change.

Update `README.md` with `python -m alembic upgrade head`, recent-run/reopen behavior, validation rules, test commands, and any environment variable actually added. If none were added, state that this feature introduces no new environment variables.

- [ ] **Step 7: Run complete backend verification**

Run: `python -m pytest backend/tests -v`

Run: `python -m alembic check`

Expected: all non-environment-dependent tests pass; PostgreSQL integration tests either pass or report their documented explicit skip.

- [ ] **Step 8: Run complete frontend verification**

Run: `cd frontend; npm test -- --run`

Run: `cd frontend; npm run lint`

Run: `cd frontend; npm run build`

Expected: all commands exit zero with no TypeScript or lint errors.

- [ ] **Step 9: Verify production images when Docker is available**

Run: `docker build -f Dockerfile -t blueprint-lab-api .`

Run: `docker build -f Dockerfile.worker -t blueprint-lab-worker .`

Run: `docker build -f Dockerfile.frontend -t blueprint-lab-frontend .`

Expected: all three images build. If Docker is unavailable, record the exact environment limitation without claiming success.

- [ ] **Step 10: Audit scope and working tree**

Run: `git -c safe.directory=C:/Users/yeekw/Documents/Blueprint-Lab diff --check`

Run: `git -c safe.directory=C:/Users/yeekw/Documents/Blueprint-Lab status --short`

Expected: no whitespace errors; `.runtime/` and `prompt/anthropic-skills/` remain untouched and untracked unless they were already user-managed.

- [ ] **Step 11: Commit Task 8**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/playwright.config.ts frontend/e2e backend/tests/test_end_to_end_run_lifecycle.py README.md docs/RUN_LIFECYCLE_AND_TOKEN_ACCOUNTING.md .env.example
git commit -m "Verify and document run tracking" -m "Add cross-layer concurrent-run and validation workflows, document exact Gemini accounting and reopening behavior, and record deployment and migration verification for the completed feature set."
```

---

## Final Acceptance Audit

- [ ] Every run-associated Gemini request has exactly one call record.
- [ ] API-reported input, output, and total fields are stored without local estimation.
- [ ] Cached, thoughts/reasoning, and extra token categories remain separate.
- [ ] Active runs show partial totals; completed runs show final totals; legacy runs show “Not recorded.”
- [ ] Experiment Condition and Word export contain token accounting.
- [ ] Shared logo links to `/` on every page with visible keyboard focus.
- [ ] Back to Control Assessment is below active progress content at bottom-right and does not cancel work.
- [ ] Multiple runs maintain isolated DB state, task execution, progress, result, error, and token totals.
- [ ] Reopening a run starts with its persisted snapshot and shows terminal results immediately.
- [ ] Duplicate submissions reuse one run and enqueue one task.
- [ ] Missing fields produce a red grouped dialog, inline ARIA errors, and focus movement.
- [ ] Backend validation creates no partial rows and enqueues no task.
- [ ] Existing experiments and source-document behavior remain readable and unchanged.
- [ ] Feature 4 remains excluded.
- [ ] Migration, backend tests, frontend tests, lint, build, and available production-image checks have recorded actual results.
