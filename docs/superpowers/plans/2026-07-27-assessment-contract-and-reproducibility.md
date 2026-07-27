# Assessment Contract and Reproducibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Blueprint Lab persist reproducible generation inputs and settings while enforcing one assessment contract across the database, backend, frontend, provider calls, and exports.

**Architecture:** Preserve the existing experiment/condition/run/prompt/assessment/question topology. Relational rows own database IDs, `assessments.raw_response_text` preserves provider evidence, and a versioned `assessments.parsed_json` holds the validated and application-enriched portable assessment. Resolve run settings before dispatch and persist the exact provider system and user inputs before executing them.

**Tech Stack:** Python 3, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL/SQLite test databases, Celery, Google GenAI, React, TypeScript, Vitest, Playwright, python-docx.

## Global Constraints

- Preserve all pre-existing uncommitted assessment-recovery work.
- Do not change expected relational behavior: independent primary keys, separate experiment/condition/run/assessment/question records, repeated traceability foreign keys, and separate evaluation/evaluation-criteria tables.
- Remove exactly `description`, `topic_area`, and `research_question` from the `experiments` table; retain `name` and `status`.
- Use `string[]` for learning objectives throughout the application.
- Remove `intended_assessment_setting` from the complete assessment contract.
- Never rewrite raw provider evidence.
- Never silently choose between conflicting legacy generated output.
- Every production behavior change begins with a failing test.
- Every commit contains an explanatory paragraph body and no attribution trailer.

---

### Task 1: Canonicalize the experiment contract

**Files:**
- Modify: `backend/models/experiment.py`
- Modify: `backend/schemas/experiment_schema.py`
- Modify: `backend/services/experiment_service.py`
- Modify: `backend/services/actual_prompt.py`
- Modify: `backend/services/prompt_generator.py`
- Modify: `backend/services/assessment_evaluation.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/InputPanelPage.tsx`
- Modify: `frontend/src/validation/experimentValidation.ts`
- Test: `backend/tests/test_experiment_models.py`
- Test: `backend/tests/test_experiment_schemas.py`
- Test: `backend/tests/test_experiment_service.py`
- Test: `backend/tests/test_actual_prompt.py`
- Test: `frontend/src/validation/experimentValidation.test.ts`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: multiline objective text entered by the user.
- Produces: `ExperimentCreate.learning_objectives: list[str]`,
  `Experiment.learning_objectives: list[str]`, and
  `parseLearningObjectives(value: string): string[]`.

- [ ] **Step 1: Write backend tests for the array contract and removed fields**

```python
def test_experiment_create_requires_nonblank_learning_objective_items():
    payload = ExperimentCreate(
        course="MSE 302",
        topic="Phase stability",
        learning_objectives=["Compare Gibbs energies", "Predict stable phases"],
        assessment_type="mixed",
        difficulty="medium",
        number_of_questions=2,
        estimated_time_minutes=30,
        cognitive_demand="apply_analyze",
        prompt_structure="openai",
        factors={},
        factor_inputs={},
    )
    assert payload.learning_objectives == [
        "Compare Gibbs energies",
        "Predict stable phases",
    ]


def test_experiment_model_has_no_removed_research_columns():
    columns = set(Experiment.__table__.columns.keys())
    assert {"description", "topic_area", "research_question"}.isdisjoint(columns)
```

- [ ] **Step 2: Run the focused backend tests and verify expected failures**

Run:

```powershell
python -m pytest backend/tests/test_experiment_schemas.py backend/tests/test_experiment_models.py -q
```

Expected: failures show `learning_objectives` still expects text and the three
obsolete columns still exist.

- [ ] **Step 3: Write frontend tests for one-line-per-objective conversion**

```typescript
expect(parseLearningObjectives(' First objective \n\nSecond objective '))
  .toEqual(['First objective', 'Second objective'])
```

Update the submission assertion in `frontend/src/App.test.tsx` to require:

```typescript
learning_objectives: ['Resolve forces', 'Check equilibrium'],
```

- [ ] **Step 4: Run the focused frontend tests and verify expected failures**

Run:

```powershell
npm test -- --run src/validation/experimentValidation.test.ts src/App.test.tsx
```

Working directory: `frontend`.

Expected: `parseLearningObjectives` is missing and the submitted payload still
contains one string.

- [ ] **Step 5: Implement the canonical experiment objective type**

Use SQLAlchemy JSON storage:

```python
learning_objectives: Mapped[list[str]] = mapped_column(
    JSON, nullable=False, default=list
)
```

Use Pydantic validation that strips every item, rejects empty arrays, rejects
blank items, and forbids coercing a scalar string into an array:

```python
learning_objectives: list[str] = Field(min_length=1)

@field_validator("learning_objectives")
@classmethod
def validate_learning_objectives(cls, values: list[str]) -> list[str]:
    cleaned = [value.strip() for value in values]
    if any(not value for value in cleaned):
        raise ValueError("Learning objectives must be nonblank")
    return cleaned
```

Remove `description`, `topic_area`, and `research_question` mappings and
dependencies. Update prompt builders to accept `Sequence[str]` and render a
stable numbered or bulleted list without joining and re-splitting values.

- [ ] **Step 6: Implement frontend conversion**

Export:

```typescript
export function parseLearningObjectives(value: string): string[] {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}
```

Keep the multiline text area state as a string for editing, but submit the
parsed array. Update TypeScript interfaces and validation so at least one
nonblank line is required.

- [ ] **Step 7: Run focused tests until green**

Run both focused commands from Steps 2 and 4. Confirm no warning or type error
is introduced.

- [ ] **Step 8: Commit the experiment contract**

```powershell
git add backend/models/experiment.py backend/schemas/experiment_schema.py backend/services/experiment_service.py backend/services/actual_prompt.py backend/services/prompt_generator.py backend/services/assessment_evaluation.py backend/tests/test_experiment_models.py backend/tests/test_experiment_schemas.py backend/tests/test_experiment_service.py backend/tests/test_actual_prompt.py frontend/src/types/index.ts frontend/src/pages/InputPanelPage.tsx frontend/src/validation/experimentValidation.ts frontend/src/validation/experimentValidation.test.ts frontend/src/App.test.tsx
git commit -m "Canonicalize experiment learning objectives" -m "Represent learning objectives as an ordered array throughout experiment submission, persistence, and prompt rendering so no stage relies on delimiter inference. Remove application dependencies on the three obsolete experiment research-description fields in preparation for the schema migration."
```

### Task 2: Persist requested and effective model configuration

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/models/run.py`
- Modify: `backend/schemas/run_schema.py`
- Modify: `backend/services/llm_client.py`
- Modify: `backend/services/run_service.py`
- Modify: `backend/services/experiment_service.py`
- Modify: `backend/workers/assessment_worker.py`
- Test: `backend/tests/test_llm_client.py`
- Test: `backend/tests/test_run_service.py`
- Test: `backend/tests/test_experiment_service.py`
- Test: `backend/tests/test_reproducibility.py`
- Test: `backend/tests/test_worker.py`

**Interfaces:**
- Produces:
  `resolve_execution_config(requested: ModelSettings | None) -> ExecutionConfigSnapshot`.
- `ExecutionConfigSnapshot` contains `schema_version`, `requested`, and
  `effective`; observed provider results remain run columns.

- [ ] **Step 1: Write failing tests for environment-backed defaults**

```python
def test_run_without_overrides_persists_effective_environment_settings(
    db, condition, monkeypatch
):
    monkeypatch.setattr(settings, "llm_provider", "google")
    monkeypatch.setattr(settings, "llm_model", "gemini-test")
    monkeypatch.setattr(settings, "llm_temperature", 0.31)
    monkeypatch.setattr(settings, "llm_top_p", 0.82)
    monkeypatch.setattr(settings, "llm_max_output_tokens", 4096)

    run = create_run(db, condition.id, [], None)

    assert run.execution_config["effective"] == {
        "provider": "google",
        "model": "gemini-test",
        "temperature": 0.31,
        "top_p": 0.82,
        "max_output_tokens": 4096,
        "provider_settings": {},
    }
```

Add a retry test that changes environment defaults after the original run and
asserts the retry retains the original effective snapshot.

- [ ] **Step 2: Run focused tests and verify null/default failures**

Run:

```powershell
python -m pytest backend/tests/test_run_service.py backend/tests/test_experiment_service.py backend/tests/test_llm_client.py -q
```

- [ ] **Step 3: Implement typed configuration resolution**

Add Pydantic models with `extra="forbid"`:

```python
class RequestedExecutionConfig(BaseModel):
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    seed: int | None = None
    provider_settings: dict[str, object] = Field(default_factory=dict)


class EffectiveExecutionConfig(BaseModel):
    provider: str
    model: str
    temperature: float
    top_p: float
    max_output_tokens: int
    seed: int | None = None
    provider_settings: dict[str, object] = Field(default_factory=dict)
```

Persist a JSON `execution_config` with schema version, requested values, and
fully resolved effective values. Retain `request_id`, `version`,
`finish_reason`, duration, and token counts as observed values. Keep compatibility
properties only where existing APIs need a staged transition.

- [ ] **Step 4: Make every provider call consume the effective snapshot**

Change `LLMClient.generate` to accept the effective keys exactly, including
`max_output_tokens`; remove the internal `max_tokens` alias. In the worker, pass
the persisted snapshot rather than resolving settings again.

- [ ] **Step 5: Verify requested/effective/observed distinctions**

Add a worker test asserting requested model, effective model, and
provider-reported `model_version` remain distinct after generation.

- [ ] **Step 6: Run focused tests until green**

Run:

```powershell
python -m pytest backend/tests/test_llm_client.py backend/tests/test_run_service.py backend/tests/test_experiment_service.py backend/tests/test_reproducibility.py backend/tests/test_worker.py -q
```

- [ ] **Step 7: Commit effective model snapshots**

```powershell
git add backend/config.py backend/models/run.py backend/schemas/run_schema.py backend/services/llm_client.py backend/services/run_service.py backend/services/experiment_service.py backend/workers/assessment_worker.py backend/tests/test_llm_client.py backend/tests/test_run_service.py backend/tests/test_experiment_service.py backend/tests/test_reproducibility.py backend/tests/test_worker.py
git commit -m "Persist effective run execution settings" -m "Resolve explicit and environment-backed model configuration before dispatch and store it as a versioned run snapshot. Reuse the persisted effective values for provider calls and retries so each run remains independently auditable when defaults later change."
```

### Task 3: Persist the exact executed prompt and enforce Concept Bridge conditions

**Files:**
- Modify: `docs/actual_prompt_template.md`
- Modify: `backend/models/run.py`
- Modify: `backend/services/actual_prompt.py`
- Modify: `backend/services/reproducibility.py`
- Modify: `backend/workers/assessment_worker.py`
- Test: `backend/tests/test_actual_prompt.py`
- Test: `backend/tests/test_prompt_generator.py`
- Test: `backend/tests/test_reproducibility.py`
- Test: `backend/tests/test_worker.py`

**Interfaces:**
- Produces:
  `build_generation_system_prompt(actual_prompt: str) -> str`,
  `Prompt.execution_system_prompt`, `Prompt.execution_user_message`, and
  `Prompt.execution_schema_version`.

- [ ] **Step 1: Write failing Concept Bridge snapshot tests**

Assert that an OFF prompt contains neither the supplied bridge text nor the
case-insensitive phrase `concept bridge`. Assert that an ON prompt contains the
supplied bridge exactly once and does not include fallback bridge content.

- [ ] **Step 2: Write a failing exact-execution-input test**

Use a recording LLM fake and assert:

```python
assert run.prompt.execution_system_prompt == llm.calls[-1]["system_prompt"]
assert run.prompt.execution_user_message == llm.calls[-1]["user_message"]
assert run.prompt.execution_system_prompt.startswith(EQUATION_GENERATION_INSTRUCTION)
```

- [ ] **Step 3: Run focused tests and verify the existing unconditional text and persistence mismatch**

Run:

```powershell
python -m pytest backend/tests/test_actual_prompt.py backend/tests/test_prompt_generator.py backend/tests/test_reproducibility.py backend/tests/test_worker.py -q
```

- [ ] **Step 4: Render Concept Bridge with conditional template blocks**

Remove unconditional bridge language from the template. Build the conditional
section in Python so OFF rendering inserts no heading, placeholder, metadata
instruction, or bridge-oriented solution language. ON rendering inserts only
the supplied content and exact condition instruction.

- [ ] **Step 5: Persist before execute**

Compose the execution system prompt and user message, assign both to the prompt
record, compute their envelope hash, flush/commit, and pass those same string
objects to `_call_gemini`. Store a version identifying the canonical provider
schema.

- [ ] **Step 6: Run focused tests until green**

Repeat the Step 3 command and inspect the snapshots for both factor states.

- [ ] **Step 7: Commit reproducible prompt execution**

```powershell
git add docs/actual_prompt_template.md backend/models/run.py backend/services/actual_prompt.py backend/services/reproducibility.py backend/workers/assessment_worker.py backend/tests/test_actual_prompt.py backend/tests/test_prompt_generator.py backend/tests/test_reproducibility.py backend/tests/test_worker.py
git commit -m "Persist exact assessment execution prompts" -m "Compose equation instructions and the generated Actual Prompt before persistence, then pass the stored system and user text unchanged to the provider. Render Concept Bridge as a true conditional block so disabled experiments contain no residual bridge instruction."
```

### Task 4: Define and enforce the canonical assessment contract

**Files:**
- Modify: `backend/schemas/assessment_schema.py`
- Modify: `backend/services/generator.py`
- Modify: `backend/services/assessment_recovery.py`
- Modify: `backend/services/actual_prompt.py`
- Modify: `backend/services/structure_system_prompts.py`
- Modify: `docs/actual_prompt_template.md`
- Modify: `frontend/src/types/index.ts`
- Test: `backend/tests/test_assessment_schema.py`
- Test: `backend/tests/test_generator.py`
- Test: `backend/tests/test_assessment_recovery.py`
- Test: `backend/tests/test_actual_prompt.py`

**Interfaces:**
- Produces: strict `ProviderAssessmentResponse` and
  `StoredAssessmentPayload`, both versioned and configured with
  `extra="forbid"`.

- [ ] **Step 1: Add representative valid and invalid contract fixtures**

The valid fixture uses:

```python
"metadata": {
    "question_title": "Phase stability",
    "question_type": "short_answer",
    "difficulty_level": "medium",
    "mse202_concepts": ["Equilibrium"],
    "mse302_concepts": ["Gibbs energy"],
    "concept_map_bridge": None,
    "materials_science_context": "Binary alloy",
    "estimated_time_minutes": 10,
    "learning_objectives": ["Compare molar Gibbs energies"],
}
```

Add invalid cases for scalar `learning_objectives`, string estimated time,
missing quality checks, malformed equations, unknown fields, and any
`intended_assessment_setting`.

- [ ] **Step 2: Run contract tests and verify current drift**

Run:

```powershell
python -m pytest backend/tests/test_assessment_schema.py backend/tests/test_generator.py backend/tests/test_assessment_recovery.py -q
```

- [ ] **Step 3: Implement strict shared models and provider schema**

Use strict metadata, option, equation, quality-check, question, and top-level
models. Generate the provider JSON schema from the provider-facing Pydantic
model rather than maintaining a handwritten parallel dictionary. Keep
application traceability out of the provider schema.

- [ ] **Step 4: Remove the intended setting and align prompt instructions**

Delete `intended_assessment_setting` from models, templates, structure prompts,
repair guidance, examples, frontend types, and recovery transformations. Use
`estimated_time_minutes: int` and `learning_objectives: list[str]` everywhere.

- [ ] **Step 5: Make recovery explicit**

Recovery may normalize documented legacy aliases but must report each action.
It may not silently discard unknown fields. Preserve raw text and validate the
recovered candidate with the same strict stored-content model.

- [ ] **Step 6: Run focused tests until green**

Repeat Step 2 and run:

```powershell
python -m pytest backend/tests/test_actual_prompt.py -q
```

- [ ] **Step 7: Commit the canonical assessment contract**

```powershell
git add backend/schemas/assessment_schema.py backend/services/generator.py backend/services/assessment_recovery.py backend/services/actual_prompt.py backend/services/structure_system_prompts.py docs/actual_prompt_template.md frontend/src/types/index.ts backend/tests/test_assessment_schema.py backend/tests/test_generator.py backend/tests/test_assessment_recovery.py backend/tests/test_actual_prompt.py
git commit -m "Enforce one assessment output contract" -m "Generate provider validation from strict Pydantic models and align prompt, repair, frontend, and stored types for learning objectives, estimated minutes, questions, equations, quality checks, and revisions. Remove intended assessment setting and reject unexpected data instead of silently dropping it."
```

### Task 5: Enrich stored assessments with real traceability IDs

**Files:**
- Modify: `backend/models/run.py`
- Modify: `backend/services/assessment_evaluation.py`
- Create: `backend/services/assessment_traceability.py`
- Modify: `backend/services/assessment_recovery_service.py`
- Modify: `backend/workers/assessment_worker.py`
- Test: `backend/tests/test_assessment_evaluation.py`
- Create: `backend/tests/test_assessment_traceability.py`
- Modify: `backend/tests/test_worker.py`

**Interfaces:**
- Produces:
  `enrich_assessment_traceability(db: Session, assessment: Assessment) -> dict`.
- Requires persisted prompt, assessment, and assessment-question IDs.

- [ ] **Step 1: Write a failing enrichment test**

Persist an experiment graph, assessment, and two questions. Assert the enriched
top-level traceability contains experiment, condition, run, prompt, assessment,
template version, assessment version, and schema version. Assert each question
contains its real question row ID and ordinal.

- [ ] **Step 2: Write a failing raw-evidence preservation test**

Capture `assessment.raw_response_text`, enrich, flush, and assert it is byte
identical. Assert `parsed_json_hash` equals the canonical hash of the enriched
payload.

- [ ] **Step 3: Run focused tests and verify traceability is currently model-authored or absent**

Run:

```powershell
python -m pytest backend/tests/test_assessment_traceability.py backend/tests/test_assessment_evaluation.py backend/tests/test_worker.py -q
```

- [ ] **Step 4: Implement transactional enrichment**

`persist_assessment_questions` first flushes question rows. The new service
deep-copies parsed JSON, replaces application-owned traceability with relational
values, validates the stored schema, assigns the enriched payload, and updates
its canonical hash. Call it in initial generation and accepted recovery flows
before document creation.

- [ ] **Step 5: Run focused tests until green**

Repeat Step 3. Confirm enrichment is idempotent and never changes raw evidence.

- [ ] **Step 6: Commit traceability enrichment**

```powershell
git add backend/models/run.py backend/services/assessment_evaluation.py backend/services/assessment_traceability.py backend/services/assessment_recovery_service.py backend/workers/assessment_worker.py backend/tests/test_assessment_evaluation.py backend/tests/test_assessment_traceability.py backend/tests/test_worker.py
git commit -m "Populate persisted assessment traceability" -m "Enrich validated assessment snapshots with real relational identifiers only after assessment and question rows have IDs. Keep raw provider text immutable and hash the final portable payload so exports and APIs carry verifiable application-owned traceability."
```

### Task 6: Add the convergent schema migration

**Files:**
- Create: `backend/migrations/versions/20260727_02_contract_convergence.py`
- Modify: `backend/tests/integration/test_research_migration.py`
- Create: `backend/tests/integration/test_contract_convergence_migration.py`
- Modify: `backend/tests/test_two_stage_migration.py`

**Interfaces:**
- Consumes revision `20260727_01`.
- Produces deployed schema matching the canonical SQLAlchemy models.

- [ ] **Step 1: Write migration tests for both legacy schema states**

Cover a database where `runs.generated_json` exists and one where the earlier
migration already removed it. Seed missing, equivalent, and conflicting
assessment cases. Also seed experiment text objectives and the three obsolete
columns.

- [ ] **Step 2: Run migration tests and verify the revision is absent**

Run:

```powershell
python -m pytest backend/tests/integration/test_contract_convergence_migration.py backend/tests/integration/test_research_migration.py backend/tests/test_two_stage_migration.py -q
```

- [ ] **Step 3: Implement objective and experiment-column migration**

Use dialect-aware JSON handling. Convert each nonblank historical objective
string to `[original_string]`, preserve existing arrays, and fail on null,
blank, or unsupported values. Drop only `description`, `topic_area`, and
`research_question`.

- [ ] **Step 4: Implement safe generated-output reconciliation**

Inspect schema state before selecting `generated_json`. Create missing
assessments from canonical JSON, accept byte/canonical equivalence, and raise a
`RuntimeError` listing conflicting run IDs. Verify counts, values, and hashes
before dropping the column.

- [ ] **Step 5: Add execution and prompt-envelope fields and constraints**

Backfill legacy runs from existing provider/model/scalar settings and current
defaults only where evidence exists. Mark unknown historical values explicitly
rather than inventing them. Backfill prompt execution fields from the best
available stored evidence and mark legacy schema versions.

- [ ] **Step 6: Normalize parsed metadata without rewriting raw text**

Remove `intended_assessment_setting`, convert known legacy estimated-time and
learning-objective forms conservatively, update schema version, and recompute
the parsed hash. Abort rather than discard unknown conflicting structures.

- [ ] **Step 7: Run migration tests until green**

Repeat Step 2 against both SQLite-compatible unit fixtures and configured
PostgreSQL integration fixtures where available.

- [ ] **Step 8: Commit the migration**

```powershell
git add backend/migrations/versions/20260727_02_contract_convergence.py backend/tests/integration/test_contract_convergence_migration.py backend/tests/integration/test_research_migration.py backend/tests/test_two_stage_migration.py
git commit -m "Migrate assessment contract evidence safely" -m "Convert learning objectives to arrays, remove the three approved experiment columns, add execution evidence fields, and reconcile legacy generated JSON without overwriting assessments. Abort on conflicts and preserve immutable raw provider responses during metadata normalization."
```

### Task 7: Remove generated JSON dependencies and align APIs and exports

**Files:**
- Modify: `backend/models/run.py`
- Modify: `backend/schemas/experiment_schema.py`
- Modify: `backend/schemas/run_schema.py`
- Modify: `backend/api/generations.py`
- Modify: `backend/api/runs.py`
- Modify: `backend/services/docx_exporter.py`
- Modify: `backend/services/document_artifact.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/AssessmentViewerPage.tsx`
- Test: `backend/tests/test_api_generations.py`
- Test: `backend/tests/test_api_runs.py`
- Test: `backend/tests/test_docx_exporter.py`
- Create: `backend/tests/test_document_artifact.py`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes only `Assessment.parsed_json` for validated assessment output.
- Exports canonical traceability and omits removed metadata.

- [ ] **Step 1: Write failing API and viewer tests**

Assert legacy generation responses source `generated_json` from
`generation.assessment.parsed_json` only. Remove the viewer fallback and test
that a run without an assessment displays no questions even if an obsolete
fixture attribute is present.

- [ ] **Step 2: Write failing DOCX traceability tests**

Render a document and inspect text for experiment ID, condition ID, run ID,
prompt ID, assessment ID, and each assessment-question ID. Assert Intended
Assessment Setting is absent and objectives render as separate array items.

- [ ] **Step 3: Run focused tests and verify fallback/export failures**

Run:

```powershell
python -m pytest backend/tests/test_api_generations.py backend/tests/test_api_runs.py backend/tests/test_docx_exporter.py backend/tests/test_document_artifact.py -q
npm test -- --run src/App.test.tsx
```

- [ ] **Step 4: Remove model and serializer dependencies**

Delete `Run.generated_json`, API field reads, experiment response remnants, and
normal worker writes. If a legacy endpoint must retain the response key, derive
its value from `assessment.parsed_json` and document it as a response alias,
never as storage.

- [ ] **Step 5: Align exports with canonical metadata**

Read traceability from enriched parsed JSON, cross-check relational IDs when
building the artifact, and render the approved metadata. Delete the intended
setting label and support objective arrays and integer estimated minutes.

- [ ] **Step 6: Run focused tests until green**

Repeat Step 3.

- [ ] **Step 7: Commit API and export convergence**

```powershell
git add backend/models/run.py backend/schemas/experiment_schema.py backend/schemas/run_schema.py backend/api/generations.py backend/api/runs.py backend/services/docx_exporter.py backend/services/document_artifact.py frontend/src/types/index.ts frontend/src/pages/AssessmentViewerPage.tsx backend/tests/test_api_generations.py backend/tests/test_api_runs.py backend/tests/test_docx_exporter.py backend/tests/test_document_artifact.py frontend/src/App.test.tsx
git commit -m "Read assessment output from canonical storage" -m "Remove runtime dependence on runs.generated_json and route APIs, the viewer, artifacts, and exports through assessments.parsed_json. Display application-generated traceability and the aligned metadata contract while omitting intended assessment setting."
```

### Task 8: Verify the complete workflow and document limitations

**Files:**
- Modify: `README.md`
- Modify: `docs/RUN_LIFECYCLE_AND_TOKEN_ACCOUNTING.md`
- Modify: tests found failing because their fixtures encode the superseded contract.

**Interfaces:**
- Produces fresh verification evidence for backend, migrations, frontend tests,
  and production build.

- [ ] **Step 1: Search for stale contract references**

Run:

```powershell
rg -n "intended_assessment_setting|generated_json|learning_objectives: str|learning_objectives: string|description|topic_area|research_question" backend frontend docs -g "!docs/superpowers/**"
```

Classify each match as a required legacy migration reference or a stale runtime
dependency. Remove stale dependencies and update fixtures through red/green
cycles.

- [ ] **Step 2: Run the full backend suite**

Run:

```powershell
python -m pytest backend/tests -q
```

Expected: zero failures. If configured PostgreSQL migration tests are skipped,
report the skip count and reason rather than claiming they ran.

- [ ] **Step 3: Run the full frontend suite**

Run:

```powershell
npm test -- --run
```

Working directory: `frontend`.

Expected: zero failures.

- [ ] **Step 4: Build the production frontend**

Run:

```powershell
npm run build
```

Working directory: `frontend`.

Expected: TypeScript and Vite complete with exit code 0.

- [ ] **Step 5: Verify migration heads and model/schema agreement**

Run:

```powershell
python -m alembic heads
python -m pytest backend/tests/integration -q
```

Expected: one head at `20260727_02`; applicable integration tests pass.

- [ ] **Step 6: Update documentation**

Document the source-of-truth rules, execution snapshot shape, exact prompt
fields, assessment schema version, immutable raw evidence, removed columns, and
limitations around historical dropped values and remote provider attachments.

- [ ] **Step 7: Inspect the final diff**

Run:

```powershell
git status --short
git diff --check
git diff --stat
```

Confirm no unrelated pre-existing recovery changes were reverted and no
generated artifacts or secrets were added.

- [ ] **Step 8: Commit documentation and fixture convergence**

```powershell
git add README.md docs/RUN_LIFECYCLE_AND_TOKEN_ACCOUNTING.md
git commit -m "Document canonical assessment evidence" -m "Explain the authoritative run, prompt, and assessment records, including effective execution snapshots, exact provider inputs, traceability enrichment, and migration limitations. This gives operators and researchers a durable reference for interpreting stored runs."
```

- [ ] **Step 9: Perform the completion audit**

Re-read the approved design and map every requirement to a passing test or
verified migration behavior. Report exact commands, pass/fail/skip counts,
files changed, migration limitations, raw-evidence behavior, and any external
provider behavior that cannot be reproduced locally.
