# Research Database Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Blueprint Lab's mutable generation persistence into an immutable, PostgreSQL-backed research log with exact run, prompt, model-setting, source-document, raw-output, and artifact provenance.

**Architecture:** Migrate `Generation` to the canonical `Run` entity while keeping temporary `/generations` compatibility routes and response aliases. Persist prompts, raw and parsed assessments, source snapshots, and artifacts as immutable run children; use Alembic for runtime schema management and retain metadata-created SQLite databases for unit tests.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy 2, Pydantic 2, Alembic, PostgreSQL with psycopg 3, SQLite, Celery, Redis/SSE, React, TypeScript, pytest, Vitest.

## Global Constraints

- PostgreSQL is the default runtime database; SQLite remains supported for unit tests.
- Every retry or regeneration creates a new run and never overwrites research evidence.
- Source files are stored as immutable byte snapshots with SHA-256 hashes and extracted text.
- Prompt hashes use canonical UTF-8 JSON with sorted keys and compact separators.
- Raw provider output is persisted before parsing or schema validation.
- Existing `/generations` endpoints remain temporary compatibility aliases.
- Stage 1 excludes rubrics, raters, evaluations, and criterion scores.
- Never persist API keys, authorization headers, or provider credentials.
- Every commit has an imperative subject and a paragraph body; never add attribution trailers.
- Preserve unrelated working-tree changes already present in the repository.

---

## File Structure

- Create `alembic.ini`, `backend/migrations/env.py`, `backend/migrations/script.py.mako`, and version files for managed schema evolution.
- Replace `backend/models/experiment.py` with focused modules: `experiment.py`, `run.py`, and `source_document.py`; re-export public models from `backend/models/__init__.py`.
- Create `backend/services/reproducibility.py` for canonical JSON and SHA-256 functions.
- Create `backend/services/source_documents.py` for validated source snapshots and text extraction.
- Create `backend/services/run_service.py` for transactional run creation and retry semantics.
- Create `backend/schemas/run_schema.py` and `backend/schemas/source_document_schema.py` for canonical API contracts.
- Create `backend/api/runs.py` and `backend/api/source_documents.py`; reduce `backend/api/generations.py` to compatibility delegation.
- Modify the LLM client and worker so request metadata and raw responses are persisted in the required order.
- Update frontend run terminology while accepting deprecated generation aliases during migration.

### Task 1: Add PostgreSQL and Alembic Infrastructure

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/config.py`
- Modify: `backend/main.py`
- Create: `alembic.ini`
- Create: `backend/migrations/env.py`
- Create: `backend/migrations/script.py.mako`
- Create: `backend/tests/test_database_config.py`

**Interfaces:**
- Produces: `settings.database_url`, defaulting to `postgresql+psycopg://blueprint:blueprint@localhost:5432/blueprint_lab`.
- Produces: Alembic configuration that imports `backend.database.Base.metadata` and reads the runtime URL from settings.
- Preserves: Tests may call `Base.metadata.create_all()` against SQLite.

- [ ] **Step 1: Write failing configuration tests**

```python
# backend/tests/test_database_config.py
from backend.config import Settings


def test_postgresql_is_the_runtime_default():
    settings = Settings(_env_file=None)
    assert settings.database_url == (
        "postgresql+psycopg://blueprint:blueprint@localhost:5432/blueprint_lab"
    )


def test_sqlite_remains_a_supported_explicit_database():
    settings = Settings(database_url="sqlite:///./test.db", _env_file=None)
    assert settings.database_url.startswith("sqlite")
```

- [ ] **Step 2: Run the tests and verify the default assertion fails**

Run: `python -m pytest backend/tests/test_database_config.py -v`

Expected: FAIL because the current default is `sqlite:///./assessment_generator.db`.

- [ ] **Step 3: Add dependencies and update configuration**

Add to `backend/requirements.txt`:

```text
alembic==1.13.3
psycopg[binary]==3.2.3
pypdf==5.1.0
```

Change `Settings.database_url` to:

```python
database_url: str = (
    "postgresql+psycopg://blueprint:blueprint@localhost:5432/blueprint_lab"
)
```

- [ ] **Step 4: Initialize Alembic and remove runtime table creation**

Configure `backend/migrations/env.py` to set `sqlalchemy.url` from `settings.database_url`, import every model through `backend.models`, and set `target_metadata = Base.metadata`. Remove the startup `Base.metadata.create_all()` handler from `backend/main.py`; do not change the test fixture.

- [ ] **Step 5: Run focused and existing startup tests**

Run: `python -m pytest backend/tests/test_database_config.py backend/tests/test_main.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/requirements.txt backend/config.py backend/main.py alembic.ini backend/migrations backend/tests/test_database_config.py
git commit -m "Add managed PostgreSQL migrations" -m "This makes PostgreSQL the default runtime database and introduces Alembic as the authoritative schema manager. SQLite metadata creation remains available to unit tests so the fast local test loop is preserved without allowing application startup to mutate managed schemas."
```

### Task 2: Introduce the Immutable Research Domain Models

**Files:**
- Modify: `backend/models/experiment.py`
- Create: `backend/models/run.py`
- Create: `backend/models/source_document.py`
- Modify: `backend/models/__init__.py`
- Modify: `backend/tests/test_experiment_models.py`
- Create: `backend/tests/test_run_models.py`

**Interfaces:**
- Produces: `Run`, `Prompt`, `Assessment`, `DocumentArtifact`, `SourceDocument`, and `RunSourceDocument` SQLAlchemy models.
- Produces: `Experiment.runs`, `Condition.runs`, and `Run.condition` relationships.
- Preserves temporarily: `Generation = Run` and `PromptRecord = Prompt` Python import aliases only; table names are canonical research names.

- [ ] **Step 1: Replace the model round-trip test with immutable-domain expectations**

```python
# backend/tests/test_run_models.py
from backend.models import Assessment, Condition, Experiment, Prompt, Run


def test_run_prompt_and_assessment_round_trip(test_db):
    experiment = Experiment(
        name="Thermodynamics factors",
        description="Factorial prompt study",
        course="MSE202",
        topic_area="Thermodynamics",
        research_question="Which factors improve assessment quality?",
        status="active",
        topic="Phase stability",
        learning_objectives="Apply Gibbs free energy.",
        assessment_type="short_answer",
        difficulty="intermediate",
        number_of_questions=1,
    )
    test_db.add(experiment)
    test_db.flush()
    condition = Condition(
        experiment_id=experiment.id,
        condition_code="C100",
        prompt_structure="openai",
        concept_bridge_enabled=True,
        few_shot_enabled=False,
        reference_content_enabled=False,
        reasoning_guidance_enabled=False,
        bloom_level_enabled=False,
        factor_inputs={},
        factor_configuration={"concept_bridge": True},
        condition_label="ConceptBridge=ON",
    )
    test_db.add(condition)
    test_db.flush()
    run = Run(condition_id=condition.id, experiment_id=experiment.id, run_number=1)
    test_db.add(run)
    test_db.flush()
    test_db.add(Prompt(run_id=run.id, prompt_structure="openai", system_prompt="S", final_prompt="U", prompt_template_version="1", prompt_generator_version="1", prompt_hash="a" * 64))
    test_db.add(Assessment(run_id=run.id, raw_response='{"questions": []}', parsed_output={"questions": []}, output_hash="b" * 64, schema_version="1"))
    test_db.commit()

    saved = test_db.get(Run, run.id)
    assert saved.condition.condition_code == "C100"
    assert saved.prompt.final_prompt == "U"
    assert saved.assessment.parsed_output == {"questions": []}
```

- [ ] **Step 2: Run the new test and verify it fails on missing models and fields**

Run: `python -m pytest backend/tests/test_run_models.py -v`

Expected: FAIL during import or model construction.

- [ ] **Step 3: Implement experiment and condition extensions**

Add the approved experiment metadata, condition code, Bloom flag, factor snapshot, timestamps, unique constraint on `(experiment_id, condition_code)`, and check constraints for experiment status. Retain existing prompt-generation fields.

- [ ] **Step 4: Implement immutable run child models**

In `backend/models/run.py`, define the exact fields and relationships from the approved design. Add unique constraints on `(condition_id, run_number)`, `Prompt.run_id`, and `Assessment.run_id`; add status checks and indexes on experiment, condition, status, and creation time. Store `raw_response` as text and canonical settings/output as JSON.

- [ ] **Step 5: Implement source provenance models**

In `backend/models/source_document.py`, define `SourceDocument` and `RunSourceDocument`, including the 20 MiB-compatible binary content column, hashes, extraction metadata, role check constraint, ordinal, and a unique constraint on `(run_id, role, ordinal)`.

- [ ] **Step 6: Add compatibility import aliases and run model tests**

In `backend/models/__init__.py` export all canonical models and add:

```python
Generation = Run
PromptRecord = Prompt
```

Run: `python -m pytest backend/tests/test_experiment_models.py backend/tests/test_run_models.py -v`

Expected: PASS after updating the old test to canonical field names without weakening its assertions.

- [ ] **Step 7: Commit**

```powershell
git add backend/models backend/tests/test_experiment_models.py backend/tests/test_run_models.py
git commit -m "Model immutable research runs" -m "This replaces the mutable generation data shape with experiments, stable conditions, immutable runs, prompts, assessments, source snapshots, and run-source associations. Compatibility import aliases limit transition churn while database constraints enforce the provenance relationships required for research logging."
```

### Task 3: Create and Verify the Data-Preserving Alembic Migration

**Files:**
- Create: `backend/migrations/versions/20260711_01_research_foundation.py`
- Create: `backend/tests/integration/test_research_migration.py`
- Create: `backend/tests/integration/conftest.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: canonical SQLAlchemy models from Task 2.
- Produces: an Alembic upgrade that renames and backfills existing data without dropping generation evidence.
- Requires: `TEST_POSTGRES_DATABASE_URL` for PostgreSQL integration tests; tests skip with an explicit reason when absent.

- [ ] **Step 1: Write a failing migration integration test**

The test must create the pre-migration tables, insert one experiment, condition, generation, prompt record, generated JSON, and artifact, run `alembic upgrade head`, and assert:

```python
assert migrated_run["run_number"] == 1
assert migrated_prompt["final_prompt"] == "legacy prompt"
assert migrated_assessment["parsed_output"] == {"questions": []}
assert migrated_artifact["content"] == b"legacy-docx"
assert migrated_prompt["prompt_generator_version"] == "legacy-unknown"
assert migrated_run["seed"] is None
```

- [ ] **Step 2: Run it and verify it fails because the migration is absent**

Run: `python -m pytest backend/tests/integration/test_research_migration.py -v`

Expected with configured PostgreSQL: FAIL because the head migration does not exist. Without the environment variable: SKIP with the documented reason.

- [ ] **Step 3: Implement the migration in safe phases**

The upgrade must:

1. Rename `generations` to `runs`.
2. Add nullable run metadata columns.
3. Populate `run_number` using `row_number() over (partition by condition_id order by created_at, id)`.
4. Rename `prompt_records` to `prompts`, `generation_id` to `run_id`, and `full_prompt` to `final_prompt`.
5. Backfill prompt version fields with `legacy-unknown` and compute hashes in Python migration code from the canonical envelope available for legacy rows.
6. Create `assessments` and copy every non-null `runs.generated_json` value into `parsed_output`; serialize the same canonical JSON into `raw_response` and hash those exact bytes.
7. Rename artifact foreign keys to `run_id` and add content hashes.
8. Create source tables.
9. Add constraints and indexes after backfill.
10. Drop `runs.generated_json` only after assessment row counts match.

The downgrade must raise an explicit Alembic `CommandError` once multiple immutable runs or source associations make lossless reversal impossible.

- [ ] **Step 4: Run migration and model tests**

Run: `python -m pytest backend/tests/integration/test_research_migration.py backend/tests/test_run_models.py -v`

Expected: PASS, or integration SKIP only when PostgreSQL is not configured.

- [ ] **Step 5: Document local PostgreSQL migration commands**

Add to `README.md`:

```powershell
$env:DATABASE_URL="postgresql+psycopg://blueprint:blueprint@localhost:5432/blueprint_lab"
python -m alembic upgrade head
python -m uvicorn backend.main:app --reload
```

- [ ] **Step 6: Commit**

```powershell
git add backend/migrations backend/tests/integration README.md
git commit -m "Migrate existing research records safely" -m "This Alembic migration renames generations to runs, moves generated output into assessment records, expands prompt provenance, and preserves existing artifacts. Backfills use explicit legacy markers instead of inventing unavailable sampling metadata, and PostgreSQL integration coverage verifies record preservation and constraints."
```

### Task 4: Add Canonical Reproducibility Hashing and Model Settings

**Files:**
- Create: `backend/services/reproducibility.py`
- Modify: `backend/services/llm_client.py`
- Modify: `backend/config.py`
- Create: `backend/tests/test_reproducibility.py`
- Modify: `backend/tests/test_llm_client.py`

**Interfaces:**
- Produces: `canonical_json(value: object) -> str`.
- Produces: `sha256_text(value: str) -> str` and `sha256_bytes(value: bytes) -> str`.
- Produces: `build_prompt_hash(system_prompt: str, final_prompt: str, prompt_structure: str, prompt_template_version: str, prompt_generator_version: str, model_settings: dict, source_hashes: list[str]) -> str`.
- Produces: `LLMResult(raw_text, provider_request_id, model_name, model_version, finish_reason)` and `LLMClient.generate(...) -> LLMResult`.

- [ ] **Step 1: Write deterministic hashing tests**

```python
def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'


def test_prompt_hash_changes_when_source_order_changes():
    common = dict(system_prompt="S", final_prompt="U", prompt_structure="openai", prompt_template_version="1", prompt_generator_version="1", model_settings={"temperature": 0.2})
    assert build_prompt_hash(**common, source_hashes=["a", "b"]) != build_prompt_hash(**common, source_hashes=["b", "a"])
```

- [ ] **Step 2: Run tests and verify imports fail**

Run: `python -m pytest backend/tests/test_reproducibility.py -v`

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement canonical serialization and hashes**

Use `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` and `hashlib.sha256(value.encode("utf-8")).hexdigest()`. The prompt envelope must include all function parameters with source hashes kept in supplied order.

- [ ] **Step 4: Make model settings explicit in the LLM client**

Add settings defaults for provider, temperature, top-p, seed, and maximum output tokens. Pass them into `GenerateContentConfig`; omit seed only if `None`. Return `LLMResult` containing the untouched response text and available provider metadata. Keep `_parse_json` as a separate pure function used after persistence by the worker.

- [ ] **Step 5: Verify hashing and client tests**

Run: `python -m pytest backend/tests/test_reproducibility.py backend/tests/test_llm_client.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/services/reproducibility.py backend/services/llm_client.py backend/config.py backend/tests/test_reproducibility.py backend/tests/test_llm_client.py
git commit -m "Capture deterministic model provenance" -m "This adds canonical serialization and SHA-256 helpers and makes sampling controls explicit in every provider request. The LLM client now returns raw text and provider metadata without parsing it, allowing workers to persist exact responses before validation."
```

### Task 5: Add Immutable Source-Document Snapshots

**Files:**
- Create: `backend/services/source_documents.py`
- Create: `backend/schemas/source_document_schema.py`
- Create: `backend/api/source_documents.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_source_documents.py`
- Create: `backend/tests/test_api_source_documents.py`

**Interfaces:**
- Produces: `create_source_document(db: Session, *, name: str, document_type: str, version: str, filename: str, media_type: str, content: bytes, description: str | None) -> SourceDocument`.
- Produces: `POST /source-documents` multipart upload and `GET /source-documents/{id}` metadata response.
- Produces: `GET /source-documents/{id}/download` for the immutable original bytes.

- [ ] **Step 1: Write validation and snapshot tests**

Test that a valid UTF-8 text upload stores exact bytes, SHA-256, decoded extracted text, and `plain-text:utf-8` extraction method. Add DOCX and PDF fixtures and assert their paragraph/page text is extracted without altering the stored bytes. Test that content over `20 * 1024 * 1024` bytes and unsupported media types raise `SourceDocumentValidationError` without inserting a row.

- [ ] **Step 2: Run tests and verify the service is missing**

Run: `python -m pytest backend/tests/test_source_documents.py -v`

Expected: FAIL on import.

- [ ] **Step 3: Implement the Stage 1 extractor boundary**

Support `text/plain`, `text/markdown`, and `application/json` using strict UTF-8 decoding, DOCX using the existing `python-docx` dependency, and PDF using `pypdf`. Define extractor dispatch as a media-type mapping. Record extraction methods as `plain-text:utf-8`, `python-docx:<installed-version>`, or `pypdf:<installed-version>`. Reject encrypted PDFs, corrupt archives, empty extraction results, and unsupported media types with stable error codes; reject oversized files with `source_document_too_large`.

- [ ] **Step 4: Implement schemas and routes**

Metadata responses include hashes and extraction information but never `content`. Download responses return stored bytes with the original filename. A duplicate upload creates a separate version record unless all metadata and the hash match, in which case return HTTP 409 with `duplicate_source_version`.

- [ ] **Step 5: Run service and API tests**

Run: `python -m pytest backend/tests/test_source_documents.py backend/tests/test_api_source_documents.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/services/source_documents.py backend/schemas/source_document_schema.py backend/api/source_documents.py backend/main.py backend/tests/test_source_documents.py backend/tests/test_api_source_documents.py
git commit -m "Store immutable source document snapshots" -m "This adds validated source uploads that retain exact file bytes, extracted text, version metadata, and integrity hashes. Metadata and download endpoints keep large binary content out of ordinary responses while ensuring every prompt source remains reproducible."
```

### Task 6: Implement Immutable Run Creation, Retry, and Canonical APIs

**Files:**
- Create: `backend/services/run_service.py`
- Create: `backend/schemas/run_schema.py`
- Create: `backend/api/runs.py`
- Modify: `backend/api/generations.py`
- Modify: `backend/api/experiments.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_run_service.py`
- Create: `backend/tests/test_api_runs.py`
- Modify: `backend/tests/test_api_generations.py`

**Interfaces:**
- Produces: `create_run(db: Session, condition_id: int, source_bindings: list[SourceBinding], model_settings: ModelSettings | None = None) -> Run`.
- Produces: `retry_run(db: Session, run_id: int) -> Run`.
- Produces: canonical `/runs` routes and deprecated `/generations` delegating aliases.

- [ ] **Step 1: Write immutable retry tests**

```python
def test_retry_creates_next_run_without_mutating_original(test_db, completed_run):
    original_hash = completed_run.prompt.prompt_hash
    retried = retry_run(test_db, completed_run.id)
    assert retried.id != completed_run.id
    assert retried.run_number == completed_run.run_number + 1
    assert retried.status == "pending"
    test_db.refresh(completed_run)
    assert completed_run.status == "complete"
    assert completed_run.prompt.prompt_hash == original_hash
```

Also test that source bindings and model settings are copied into the retry snapshot and that unknown run or condition IDs return 404 through the API.

- [ ] **Step 2: Run tests and verify the service is missing**

Run: `python -m pytest backend/tests/test_run_service.py backend/tests/test_api_runs.py -v`

Expected: FAIL on imports or missing routes.

- [ ] **Step 3: Implement transactional run numbering**

For PostgreSQL, lock the condition row with `SELECT ... FOR UPDATE`, query the maximum run number, and insert the next value in the same transaction. For SQLite tests, the same code path may omit unsupported lock behavior but must retain the unique constraint. Retry `IntegrityError` up to three times with a fresh transaction.

- [ ] **Step 4: Implement source bindings and canonical schemas**

Validate role values and ordinal uniqueness before insertion. Snapshot canonical model settings onto the run. Run detail responses include prompt provenance, parsed assessment, source metadata and roles, error metadata, and artifact availability, but exclude file bytes and raw response by default. Provide `include_raw_response=true` for authorized research retrieval in the current single-user deployment.

- [ ] **Step 5: Implement canonical and compatibility routes**

Add:

```text
POST /conditions/{condition_id}/runs
GET  /runs/{run_id}
POST /runs/{run_id}/retry
GET  /runs/{run_id}/export-docx
```

Make `/generations/{id}`, `/generations/{id}/regenerate`, and export delegate to the same services. Regenerate returns `{run_id, generation_id, status}` where both IDs identify the new run, and adds `Deprecation: true` and a `Link` header pointing to the canonical route.

- [ ] **Step 6: Update experiment creation to call `create_run`**

The experiment endpoint creates the experiment and condition, then calls `create_run` rather than constructing a generation directly. Its compatibility response exposes both `runs` and deprecated `generations` during the frontend transition.

- [ ] **Step 7: Run API and service tests**

Run: `python -m pytest backend/tests/test_run_service.py backend/tests/test_api_runs.py backend/tests/test_api_generations.py backend/tests/test_api_experiments.py -v`

Expected: PASS, including assertions that the original completed run remains intact.

- [ ] **Step 8: Commit**

```powershell
git add backend/services/run_service.py backend/schemas/run_schema.py backend/api/runs.py backend/api/generations.py backend/api/experiments.py backend/main.py backend/tests/test_run_service.py backend/tests/test_api_runs.py backend/tests/test_api_generations.py backend/tests/test_api_experiments.py
git commit -m "Create immutable research run APIs" -m "This introduces canonical run creation, retrieval, retry, and export endpoints with transactional run numbering and source bindings. Deprecated generation routes now delegate to immutable behavior so regeneration preserves every prior prompt, assessment, and artifact."
```

### Task 7: Persist Prompt, Raw Output, Assessment, and Artifact in Order

**Files:**
- Modify: `backend/workers/assessment_worker.py`
- Modify: `backend/services/generator.py`
- Modify: `backend/services/docx_exporter.py`
- Modify: `backend/tests/test_worker.py`
- Modify: `backend/tests/test_generator.py`

**Interfaces:**
- Consumes: `LLMClient.generate() -> LLMResult` and reproducibility helpers from Task 4.
- Produces: worker task `run_generation_pipeline(run_id: int) -> None`.
- Guarantees: prompt commit precedes provider call; raw assessment response commit precedes parsing.

- [ ] **Step 1: Write worker-ordering and parse-failure tests**

Add a successful test asserting prompt, provider metadata, raw response, parsed output, hashes, and artifact are stored. Add a malformed-response test asserting:

```python
assert run.status == "error"
assert run.assessment.raw_response == "not-json"
assert run.assessment.parsed_output is None
assert run.assessment.output_hash == sha256_text("not-json")
assert run.error_type == "assessment_parse_error"
assert run.prompt.prompt_hash
```

- [ ] **Step 2: Run tests and verify current worker fails the new persistence contract**

Run: `python -m pytest backend/tests/test_worker.py -v`

Expected: FAIL because the current worker parses inside the client and stores generated JSON on the run.

- [ ] **Step 3: Separate raw generation from parsing**

Change `generate_questions` to accept raw text and return `AssessmentGenerationResponse` after calling `_parse_json`. Do not call the provider from this function.

- [ ] **Step 4: Rewrite worker persistence sequence**

The worker must:

1. Load run, condition, and ordered sources.
2. Store and commit `Prompt` with its canonical hash.
3. Call the model with settings copied from `Run.model_settings`.
4. Store and commit `Assessment.raw_response`, `output_hash`, and provider metadata.
5. Parse and validate; update `Assessment.parsed_output` and commit.
6. Generate and store the immutable artifact with content hash.
7. Mark the run complete and publish run-aware progress events.

Sanitize exceptions into stable `error_type` and bounded `error_message`; never store request headers or credentials.

- [ ] **Step 5: Update DOCX metadata terminology**

Change exporter parameters and document metadata from assessment/generation IDs to `run_id`, `prompt_id`, condition code, and run number. Keep visible assessment content unchanged.

- [ ] **Step 6: Run worker, generator, and exporter tests**

Run: `python -m pytest backend/tests/test_worker.py backend/tests/test_generator.py backend/tests/test_docx_exporter.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/workers/assessment_worker.py backend/services/generator.py backend/services/docx_exporter.py backend/tests/test_worker.py backend/tests/test_generator.py backend/tests/test_docx_exporter.py
git commit -m "Persist complete run provenance in order" -m "This rewrites the worker so prompts are committed before provider calls and raw responses are committed before parsing. Successful and malformed outputs now retain exact hashes, provider metadata, assessment records, artifacts, and sanitized failure evidence under an immutable run."
```

### Task 8: Migrate the Frontend to Run Terminology

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/runs.ts`
- Modify: `frontend/src/api/generations.ts`
- Modify: `frontend/src/api/experiments.ts`
- Modify: `frontend/src/store/runStore.ts`
- Modify: `frontend/src/store/runStore.test.ts`
- Modify: `frontend/src/pages/ProgressPage.tsx`
- Modify: `frontend/src/pages/AssessmentViewerPage.tsx`
- Modify: `frontend/src/hooks/useSSE.ts`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Produces: frontend `Run` type and `runsApi` client.
- Accepts temporarily: SSE events with `run_id` or deprecated `generation_id`.
- Guarantees: retry selects the newly created run while retaining the original in comparison history.

- [ ] **Step 1: Update store tests for immutable retry**

Add a test that starts with completed run 1, handles a retry response for run 2, and asserts both remain in state while run 2 becomes selected. Add an SSE compatibility test that normalizes `generation_id` to `run_id`.

- [ ] **Step 2: Run frontend tests and verify they fail**

Run: `npm test -- --run` from `frontend`.

Expected: FAIL on missing run types or immutable retry behavior.

- [ ] **Step 3: Add run types and API client**

Define `Run`, `RunSource`, `PromptProvenance`, and `AssessmentOutput`. Keep `type Generation = Run` only in `types/index.ts` during transition. Add `runsApi.get`, `runsApi.retry`, and `runsApi.exportDocx` using canonical routes. Make `generationsApi` a deprecated wrapper around `runsApi`.

- [ ] **Step 4: Update store, pages, and SSE normalization**

Use `runs` internally. When an experiment response contains only deprecated `generations`, normalize it once at the API boundary. Retry adds the returned run instead of replacing or clearing the selected run. Progress labels display condition code and run number.

- [ ] **Step 5: Run frontend verification**

Run from `frontend`:

```powershell
npm test -- --run
npm run build
```

Expected: all tests PASS and production build succeeds.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src
git commit -m "Adopt immutable runs in the frontend" -m "This moves frontend state, API calls, progress events, retry behavior, and assessment selection to canonical run terminology. Compatibility normalization accepts legacy generation fields while ensuring a retry adds a new comparison result instead of replacing research history."
```

### Task 9: Complete End-to-End Verification and Documentation

**Files:**
- Create: `backend/tests/test_research_run_workflow.py`
- Modify: `README.md`
- Modify: `.env.example` if present; otherwise create `.env.example`

**Interfaces:**
- Verifies all interfaces produced by Tasks 1–8.
- Documents the Stage 1/Stage 2 boundary and compatibility deprecation.

- [ ] **Step 1: Write the end-to-end research workflow test**

Using a mocked provider and real SQLite test database, create an experiment and condition, bind a source snapshot, execute run 1, retry into run 2, execute run 2, and assert:

```python
assert run_1.id != run_2.id
assert run_1.run_number == 1
assert run_2.run_number == 2
assert run_1.prompt.prompt_hash
assert run_2.prompt.prompt_hash
assert run_1.assessment.raw_response
assert run_2.assessment.raw_response
assert run_1.source_bindings[0].source_document.content == uploaded_bytes
assert run_1.document_artifact.content
assert run_2.document_artifact.content
```

- [ ] **Step 2: Run the new workflow test**

Run: `python -m pytest backend/tests/test_research_run_workflow.py -v`

Expected: PASS; if it fails, fix only the responsible implementation and add a focused regression assertion.

- [ ] **Step 3: Document configuration and research guarantees**

Update `README.md` with PostgreSQL setup, `alembic upgrade head`, source upload support and 20 MiB limit, canonical run endpoints, retry immutability, hash semantics, compatibility routes, integration-test configuration, and the explicit Stage 2 evaluation boundary. Add `.env.example` with non-secret local defaults and empty API key placeholders.

- [ ] **Step 4: Run full backend verification**

Run:

```powershell
python -m pytest backend/tests -v
python -m alembic check
```

Expected: all unit tests PASS; PostgreSQL tests PASS when `TEST_POSTGRES_DATABASE_URL` is configured or report their explicit SKIP reason. `alembic check` reports no new upgrade operations.

- [ ] **Step 5: Run full frontend verification**

Run from `frontend`:

```powershell
npm test -- --run
npm run build
```

Expected: all tests PASS and build succeeds.

- [ ] **Step 6: Check migration and repository hygiene**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors. Confirm unrelated pre-existing changes remain unstaged and unchanged.

- [ ] **Step 7: Commit**

```powershell
git add backend/tests/test_research_run_workflow.py README.md .env.example
git commit -m "Document and verify the research database foundation" -m "This adds end-to-end coverage proving that repeated runs retain independent prompts, outputs, sources, and artifacts. The documentation explains PostgreSQL migrations, provenance guarantees, compatibility behavior, test configuration, and the evaluation features intentionally deferred to Stage 2."
```

## Final Verification Checklist

- [ ] `python -m pytest backend/tests -v` passes.
- [ ] PostgreSQL migration tests pass with `TEST_POSTGRES_DATABASE_URL` configured.
- [ ] `python -m alembic upgrade head` succeeds on a fresh PostgreSQL database.
- [ ] Migration from the legacy schema preserves prompts, outputs, and artifacts.
- [ ] `python -m alembic check` reports no pending model changes.
- [ ] `npm test -- --run` passes from `frontend`.
- [ ] `npm run build` succeeds from `frontend`.
- [ ] Retrying a completed or failed run creates the next run number and leaves the original unchanged.
- [ ] Raw malformed provider output remains retrievable after parsing fails.
- [ ] Source bytes, extracted text, roles, order, and hashes are traceable from every run.
- [ ] Compatibility routes return deprecation metadata and never invoke destructive regeneration.
- [ ] No secrets appear in persisted settings, errors, fixtures, logs, or committed environment files.
