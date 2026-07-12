# Two-Stage Actual Prompt Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Blueprint Lab's deterministic single-call assessment prompt path with a reproducible two-call pipeline that generates and validates an Actual Prompt before using it as the controlling instruction for assessment generation.

**Architecture:** Separate, versioned OpenAI and Anthropic Structure System Prompts control the first LLM call. That call receives only Assessment Details and Prompt Design Factors and produces a raw Actual Prompt; the second call uses that raw prompt as its system instruction and receives ordered source content separately. The database preserves the exact envelopes, hashes, and provider metadata for both calls.

**Tech Stack:** Python 3.9+, FastAPI, SQLAlchemy 2, Pydantic, Alembic, Celery, Google GenAI client, pytest, PostgreSQL/SQLite test database.

## Global Constraints

- Both calls use the same model and canonical `run.model_settings`.
- Uploaded source content is excluded from the first call and included only in the second call.
- The raw Actual Prompt is never silently rewritten or repaired.
- The Actual Prompt is the second call's controlling system instruction; no competing assessment system prompt is added.
- Raw responses are committed before their corresponding validation or parsing step.
- Explicit run retries create new immutable runs and repeat both calls.
- Commits contain a subject and an explanatory paragraph body, with no attribution trailers.

---

### Task 1: Persist Both LLM Call Envelopes and Metadata

**Files:**
- Create: `backend/migrations/versions/20260712_01_two_stage_prompts.py`
- Modify: `backend/models/run.py`
- Modify: `backend/services/reproducibility.py`
- Modify: `backend/tests/test_run_models.py`
- Modify: `backend/tests/test_reproducibility.py`
- Test: `backend/tests/test_research_migration.py`

**Interfaces:**
- Produces: `Prompt.structure_system_prompt`, `Prompt.structure_input`, `Prompt.actual_prompt`, `Prompt.actual_prompt_hash`, structure-call metadata, `Prompt.generation_context`, and `Prompt.generation_envelope_hash`.
- Produces: `build_actual_prompt_hash(*, structure_system_prompt: str, structure_input: str, actual_prompt: str, prompt_structure: str, structure_prompt_version: str, actual_prompt_generator_version: str, model_settings: dict) -> str`.
- Produces: `build_generation_envelope_hash(*, actual_prompt: str, generation_context: str, model_settings: dict, source_hashes: list[str]) -> str`.
- Consumes: existing canonical JSON and SHA-256 helpers.

- [ ] **Step 1: Write failing model and hash tests**

Add tests that construct a `Prompt` with explicit two-stage evidence and assert round-trip persistence. Replace the old single-envelope hash test with exact stage-specific tests:

```python
def test_actual_prompt_hash_changes_with_structure_input():
    common = dict(
        structure_system_prompt="structure",
        actual_prompt="actual",
        prompt_structure="openai",
        structure_prompt_version="2",
        actual_prompt_generator_version="2",
        model_settings={"temperature": 0.2},
    )
    assert build_actual_prompt_hash(**common, structure_input="A") != build_actual_prompt_hash(
        **common, structure_input="B"
    )


def test_generation_envelope_hash_changes_with_source_order():
    common = dict(
        actual_prompt="actual",
        generation_context="context",
        model_settings={"temperature": 0.2},
    )
    assert build_generation_envelope_hash(**common, source_hashes=["a", "b"]) != \
        build_generation_envelope_hash(**common, source_hashes=["b", "a"])
```

The model test must assert all new text, version, hash, request ID, model name/version, finish reason, and duration fields survive `flush()`, `expire_all()`, and reload.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `python -m pytest backend/tests/test_run_models.py backend/tests/test_reproducibility.py -v`

Expected: FAIL because the two-stage columns and hash functions do not exist.

- [ ] **Step 3: Add the two-stage model fields and hashes**

Refactor `Prompt` so its canonical fields are explicit:

```python
class Prompt(Base):
    # existing id, run_id, prompt_structure, created_at
    structure_system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    structure_input: Mapped[str] = mapped_column(Text, nullable=False)
    actual_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    actual_prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    structure_prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    actual_prompt_generator_version: Mapped[str] = mapped_column(String, nullable=False)
    structure_request_id: Mapped[Optional[str]] = mapped_column(String)
    structure_model: Mapped[Optional[str]] = mapped_column(String)
    structure_model_version: Mapped[Optional[str]] = mapped_column(String)
    structure_finish_reason: Mapped[Optional[str]] = mapped_column(String)
    structure_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    generation_context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    generation_envelope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
```

Keep `system_prompt`, `final_prompt`, `template_version`, `generator_version`, and `prompt_hash` only as SQLAlchemy synonyms for compatibility, mapped respectively to the explicit first-stage fields and `actual_prompt_hash`. Do not retain duplicate writable columns.

Add canonical hash functions:

```python
def build_actual_prompt_hash(*, structure_system_prompt: str, structure_input: str,
                             actual_prompt: str, prompt_structure: str,
                             structure_prompt_version: str,
                             actual_prompt_generator_version: str,
                             model_settings: dict) -> str:
    return sha256_text(canonical_json({
        "structure_system_prompt": structure_system_prompt,
        "structure_input": structure_input,
        "actual_prompt": actual_prompt,
        "prompt_structure": prompt_structure,
        "structure_prompt_version": structure_prompt_version,
        "actual_prompt_generator_version": actual_prompt_generator_version,
        "model_settings": model_settings,
    }))


def build_generation_envelope_hash(*, actual_prompt: str, generation_context: str,
                                   model_settings: dict,
                                   source_hashes: list[str]) -> str:
    return sha256_text(canonical_json({
        "actual_prompt": actual_prompt,
        "generation_context": generation_context,
        "model_settings": model_settings,
        "source_hashes": source_hashes,
    }))
```

- [ ] **Step 4: Add and verify the online Alembic migration**

Create revision `20260712_01` with `down_revision = "20260711_01"`. Rename existing columns to their explicit equivalents, add the new non-null evidence fields initially nullable, backfill legacy rows without inventing provider metadata, calculate both hashes in Python using canonical JSON, then make evidence columns non-null. Preserve legacy prompt text exactly. Refuse offline mode because Python hashing is required. Add a migration test that upgrades from `20260711_01`, compares pre/post prompt text, and verifies 64-character hashes.

Run: `python -m pytest backend/tests/test_run_models.py backend/tests/test_reproducibility.py backend/tests/test_research_migration.py -v`

Expected: PASS, with the PostgreSQL migration test explicitly skipped when `TEST_POSTGRES_DATABASE_URL` is absent.

- [ ] **Step 5: Commit the persistence foundation**

```powershell
git add backend/models/run.py backend/services/reproducibility.py backend/migrations/versions/20260712_01_two_stage_prompts.py backend/tests/test_run_models.py backend/tests/test_reproducibility.py backend/tests/test_research_migration.py
git commit -m "Persist two-stage prompt evidence" -m "This introduces explicit storage and canonical hashes for the Structure System Prompt, first-call input, raw Actual Prompt, generation context, and first-call provider metadata. The migration preserves legacy prompt evidence while preparing immutable runs to reconstruct both LLM calls."
```

---

### Task 2: Build and Validate Provider-Specific Actual Prompts

**Files:**
- Create: `backend/services/structure_system_prompts.py`
- Create: `backend/services/actual_prompt.py`
- Modify: `backend/services/prompt_generator.py`
- Delete: `backend/services/prompt_factors.py`
- Create: `backend/tests/test_actual_prompt.py`
- Modify: `backend/tests/test_prompt_generator.py`
- Delete: `backend/tests/test_prompt_factors.py`

**Interfaces:**
- Produces: `get_structure_system_prompt(prompt_structure: PromptStructure) -> tuple[str, str]`, returning prompt text and version.
- Produces: `build_structure_input(*, course: str, topic: str, learning_objectives: str, assessment_type: str, difficulty: str, number_of_questions: int, factors: PromptFactors, factor_inputs: dict[str, str]) -> str`.
- Produces: `validate_actual_prompt(prompt_structure: PromptStructure, raw_text: str) -> None`.
- Consumes: `PromptFactors`, experiment values, and condition factor inputs.

- [ ] **Step 1: Write failing structure-selection and serialization tests**

Test that OpenAI and Anthropic select different non-empty Structure System Prompts; that the input labels Assessment Details and Prompt Design Factors; that disabled factors record `OFF` without injecting their absent content; and that no uploaded source-document text parameter exists.

```python
def test_structure_input_contains_details_and_enabled_factor_values_only():
    text = build_structure_input(
        course="MSE202", topic="Gibbs Phase Rule",
        learning_objectives="Apply the phase rule.",
        assessment_type="short_answer", difficulty="medium",
        number_of_questions=1,
        factors=PromptFactors(concept_bridge=True),
        factor_inputs={"concept_bridge": "Criterion for equilibrium",
                       "few_shot": "must not appear"},
    )
    assert "Assessment Details" in text
    assert "ConceptBridge=ON" in text
    assert "Criterion for equilibrium" in text
    assert "must not appear" not in text
```

- [ ] **Step 2: Write failing validation tests**

Cover empty output, fenced output, leading commentary, missing OpenAI sections, missing/duplicate/unbalanced Anthropic tags, and valid versions of both structures. Use the exact required sections defined in each Structure System Prompt rather than accepting arbitrary Markdown or XML.

Run: `python -m pytest backend/tests/test_actual_prompt.py backend/tests/test_prompt_generator.py -v`

Expected: FAIL because the structure prompt module, serializer, and validator do not exist.

- [ ] **Step 3: Implement separate Structure System Prompts**

Define `OPENAI_STRUCTURE_SYSTEM_PROMPT` and `ANTHROPIC_STRUCTURE_SYSTEM_PROMPT` in one focused module. The OpenAI prompt requires `# Role`, `# Personality`, `# Goal`, `# Measure of Success`, `# Constraints`, `# Output`, and `# Stop Rules`. The Anthropic prompt requires exactly the project's documented `<context>`, `<task>`, `<constraints>`, `<verification>`, `<output_format>`, and `<reasoning_guidance>` sections. Both prompts instruct the model to return only the completed Actual Prompt without fences or commentary and to incorporate only enabled factor inputs.

Set `STRUCTURE_PROMPT_VERSION = "2"` and return it with the selected prompt. Keep structure wording centralized so validation and version changes remain deliberate.

- [ ] **Step 4: Implement deterministic first-call input and strict validation**

Implement `build_structure_input` as deterministic Markdown containing only research values, the complete ON/OFF condition label, and enabled factor values. Implement `ActualPromptValidationError(ValueError)` and validation that strips nothing except for checking whether `raw_text.strip() == raw_text`; reject leading/trailing commentary, code fences, missing required sections, duplicated Anthropic sections, and unbalanced tags. The function returns `None` on success and never returns a modified prompt.

Update `generate_prompt` to become a compatibility wrapper around `build_structure_input`, or remove its runtime use if no caller remains. It must no longer produce the Actual Prompt deterministically.

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest backend/tests/test_actual_prompt.py backend/tests/test_prompt_generator.py -v`

Expected: PASS.

```powershell
git add backend/services/structure_system_prompts.py backend/services/actual_prompt.py backend/services/prompt_generator.py backend/tests/test_actual_prompt.py backend/tests/test_prompt_generator.py backend/services/prompt_factors.py backend/tests/test_prompt_factors.py
git commit -m "Generate provider-structured prompt inputs" -m "This adds independent OpenAI and Anthropic Structure System Prompts, deterministic experiment-input serialization, and strict validation for raw Actual Prompts. It removes the deterministic builder that incorrectly treated the assessment system prompt as the generated prompt."
```

---

### Task 3: Assemble Ordered Generation Context

**Files:**
- Create: `backend/services/generation_context.py`
- Create: `backend/tests/test_generation_context.py`

**Interfaces:**
- Produces: `build_generation_context(bindings: Sequence[RunSourceDocument]) -> str`.
- Consumes: immutable `RunSourceDocument` bindings and their `SourceDocument` snapshots.

- [ ] **Step 1: Write failing ordered-context tests**

Create bindings out of database insertion order and assert output order is `(ordinal, id)`. Assert each block includes role, source name, version, and exact extracted text. Assert binary-only sources use decoded UTF-8 text when valid and fail clearly when no usable text exists. Assert an empty binding list returns the exact neutral trigger `Generate the assessment now.`.

```python
def test_empty_sources_use_neutral_generation_trigger():
    assert build_generation_context([]) == "Generate the assessment now."
```

- [ ] **Step 2: Run the test and verify failure**

Run: `python -m pytest backend/tests/test_generation_context.py -v`

Expected: FAIL because `generation_context` does not exist.

- [ ] **Step 3: Implement exact ordered context assembly**

Sort by `(ordinal, id)`. Render each source as a stable block:

```text
<source role="course_syllabus" ordinal="0" name="Course syllabus" version="2026.1">
exact immutable snapshot text
</source>
```

Escape attribute values, but do not normalize or trim source text. Verify `sha256(included bytes)` equals `included_text_hash` before returning the context; raise `SourceSnapshotError` on mismatch or unavailable text. This protects the second-call envelope from executing content different from the recorded snapshot.

- [ ] **Step 4: Run tests and commit**

Run: `python -m pytest backend/tests/test_generation_context.py -v`

Expected: PASS.

```powershell
git add backend/services/generation_context.py backend/tests/test_generation_context.py
git commit -m "Build immutable generation context" -m "This assembles source snapshots in recorded binding order for the second LLM call and supplies a neutral trigger when no sources exist. Hash verification prevents generation from using context that differs from the immutable run evidence."
```

---

### Task 4: Orchestrate the Two LLM Calls

**Files:**
- Modify: `backend/workers/assessment_worker.py`
- Modify: `backend/services/generator.py`
- Modify: `backend/tests/test_worker.py`
- Modify: `backend/tests/test_research_run_workflow.py`

**Interfaces:**
- Consumes: `get_structure_system_prompt`, `build_structure_input`, `validate_actual_prompt`, `build_generation_context`, both stage hash functions, and `LLMClient.generate`.
- Produces: a complete immutable run containing both call envelopes, raw responses, metadata, parsed assessment, and DOCX artifact.

- [ ] **Step 1: Rewrite the successful worker test for two calls**

Set `llm.generate.side_effect` to an Actual Prompt result followed by valid assessment JSON. Assert exactly two calls and identical `model_settings`:

```python
assert llm.generate.call_args_list[0].kwargs == {
    "system_prompt": expected_structure_system_prompt,
    "user_message": expected_structure_input,
    "model_settings": generation_fixture.model_settings,
}
assert llm.generate.call_args_list[1].kwargs == {
    "system_prompt": actual_prompt,
    "user_message": expected_generation_context,
    "model_settings": generation_fixture.model_settings,
}
```

Also assert the first result's metadata is stored on `Prompt`, the second result's metadata is stored on `Run`, both hashes are populated, and the document is produced.

- [ ] **Step 2: Add failing evidence and failure-stage tests**

Add tests proving:

- malformed Actual Prompt is committed and classified as `actual_prompt_validation_error` without a second call;
- first provider failure becomes `actual_prompt_provider_error`;
- second provider failure becomes `generation_provider_error`;
- malformed assessment JSON remains `assessment_parse_error` with its raw response committed;
- source text appears only in the second call;
- a retry produces a new run and invokes two fresh calls.

Patch the Celery task's retry method where provider failures are exercised so tests assert classification without scheduling a real retry.

Run: `python -m pytest backend/tests/test_worker.py backend/tests/test_research_run_workflow.py -v`

Expected: FAIL because the worker still performs one call under `_QUESTION_GENERATOR_SYSTEM_PROMPT`.

- [ ] **Step 3: Replace the single-call worker path**

Remove `_QUESTION_GENERATOR_SYSTEM_PROMPT`. In `run_generation_pipeline`:

1. Build and call the selected Structure System Prompt.
2. Immediately create and commit `Prompt` with the raw Actual Prompt, first-call input, hash, version, and provider metadata.
3. Validate the committed Actual Prompt; on failure, set `actual_prompt_validation_error` and return.
4. Build and persist the exact Generation context and generation-envelope hash.
5. Call `llm.generate(system_prompt=prompt.actual_prompt, user_message=prompt.generation_context, model_settings=run.model_settings)`.
6. Immediately create and commit `Assessment` and second-call metadata.
7. Parse, export, and complete using the existing downstream stages.

Measure each call separately with `time.perf_counter()`. Store the first-call duration in `Prompt.structure_duration_ms` and the second-call duration in the existing `Run.duration_ms` field, whose compatibility synonym is already `generation_time_ms`. Do not store their sum in either field.

Refactor repeated provider exception handling into a small stage-aware helper so database rollback, evidence status, progress publication, and Celery retry behavior remain consistent.

- [ ] **Step 4: Run worker and workflow tests**

Run: `python -m pytest backend/tests/test_worker.py backend/tests/test_research_run_workflow.py -v`

Expected: PASS, with each successful run making exactly two provider calls.

- [ ] **Step 5: Commit the two-call orchestration**

```powershell
git add backend/workers/assessment_worker.py backend/services/generator.py backend/tests/test_worker.py backend/tests/test_research_run_workflow.py
git commit -m "Run two-stage assessment generation" -m "This changes each immutable run to generate and validate an Actual Prompt before executing it as the assessment call's controlling instruction. It isolates source context to the second call and preserves raw evidence and stage-specific failures before validation or parsing."
```

---

### Task 5: Expose Clear Two-Stage Provenance

**Files:**
- Modify: `backend/api/runs.py`
- Modify: `backend/tests/test_api_runs.py`
- Modify: `README.md`

**Interfaces:**
- Produces: explicit Actual Prompt provenance in `GET /runs/{run_id}`.
- Consumes: the two-stage `Prompt` fields from Task 1.

- [ ] **Step 1: Write failing API provenance tests**

Update the canonical run-detail test to assert the prompt object uses explicit keys:

```python
assert detail["prompt"]["actual_prompt_hash"] == run.prompt.actual_prompt_hash
assert detail["prompt"]["structure_prompt_version"] == "2"
assert "structure_system_prompt" not in detail["prompt"]
assert "actual_prompt" not in detail["prompt"]

raw_detail = client.get(f"/runs/{run.id}?include_raw_response=true").json()
assert raw_detail["prompt"]["structure_system_prompt"] == "OpenAI structure rules"
assert raw_detail["prompt"]["structure_input"] == "Assessment Details: MSE202"
assert raw_detail["prompt"]["actual_prompt"] == "# Role\nAssessment generator"
assert raw_detail["prompt"]["generation_context"] == "Generate the assessment now."
```

Default responses expose hashes, versions, and provider metadata but not raw instructions or source context. `include_raw_response=true` exposes exact first- and second-stage raw evidence for the existing single-user research deployment.

- [ ] **Step 2: Run the API test and verify failure**

Run: `python -m pytest backend/tests/test_api_runs.py -v`

Expected: FAIL because `run_detail` still returns ambiguous `text`, `hash`, `template_version`, and `generator_version` keys.

- [ ] **Step 3: Update run detail and documentation**

Replace ambiguous prompt response keys with the approved terminology. Include both calls' request IDs, model versions, finish reasons, durations, and envelope hashes. Keep raw evidence behind `include_raw_response=true`.

Update README's stage-boundary and research-guarantee sections to state that every run records a Structure System Prompt call and an Actual-Prompt-controlled Generation call, both using the same model settings, with sources isolated to Generation.

- [ ] **Step 4: Run API tests and commit**

Run: `python -m pytest backend/tests/test_api_runs.py -v`

Expected: PASS.

```powershell
git add backend/api/runs.py backend/tests/test_api_runs.py README.md
git commit -m "Expose two-stage run provenance" -m "This updates run retrieval and documentation to use Structure System Prompt, Actual Prompt, and Generation terminology. Researchers can inspect hashes and provider metadata by default and opt into exact raw evidence without ambiguous legacy prompt labels."
```

---

### Task 6: Verify the Complete Migration and Pipeline

**Files:**
- Modify if required by failures: only files already listed in Tasks 1-5

**Interfaces:**
- Consumes: the complete two-stage implementation.
- Produces: verification evidence that backend behavior, migrations, and frontend compatibility remain intact.

- [ ] **Step 1: Run targeted prompt and worker coverage**

Run:

```powershell
python -m pytest backend/tests/test_actual_prompt.py backend/tests/test_generation_context.py backend/tests/test_worker.py backend/tests/test_research_run_workflow.py backend/tests/test_reproducibility.py -v
```

Expected: PASS.

- [ ] **Step 2: Run the complete backend suite**

Run: `python -m pytest backend/tests -v`

Expected: PASS, except the documented PostgreSQL-only skip when `TEST_POSTGRES_DATABASE_URL` is not configured.

- [ ] **Step 3: Verify Alembic state**

Run: `python -m alembic check`

Expected: `No new upgrade operations detected.`

Run: `python -m alembic heads`

Expected: `20260712_01 (head)`.

- [ ] **Step 4: Run frontend regression checks**

Run: `npm test -- --run`

Working directory: `frontend`

Expected: PASS.

Run: `npm run build`

Working directory: `frontend`

Expected: successful TypeScript and Vite build.

- [ ] **Step 5: Review the final diff and commit verification fixes only if needed**

Run: `git diff --check`

Expected: no whitespace errors.

If verification reveals a failure, return to the task that owns the failing behavior, add a regression test there, apply the smallest fix, rerun that task's focused tests and this complete verification task, and commit using that task's explicit file list. Do not create an empty verification commit when no fixes were needed.
