# Plan 5: Agentic DOCX Tools and Visual Revision Loop

**Goal:** Add a reliable LLM-authored Word workflow in which the assessment JSON is immutable, Gemini designs and revises the complete document through typed DOCX tools, trusted application code creates the DOCX, LibreOffice renders every draft, and a bounded multimodal review loop produces one verified canonical artifact.

**Depends on:** Plans 1 through 4. Assessment versioning, canonical pointers, model-call usage, recovery display, Redis/Celery, and the existing sandbox security posture must remain intact.

**Architecture:** The assessment-generation LLM remains responsible for question-and-solution JSON. A separate DOCX design agent receives an immutable content catalog, design contract, and tool declarations. It creates and edits a persistent document workspace through structured calls. The tool executor uses trusted `python-docx` and existing OMML utilities; it never evaluates model-authored Python or arbitrary XML. LibreOffice renders each draft to PDF and bounded page images. Machine validators and Gemini review the render. Gemini may submit targeted revision calls within a fixed iteration budget. Only a machine-valid, review-approved result is canonicalized.

**Backend name:** Add `agentic_tools` as a third `DOCX_GENERATION_BACKEND` value. Preserve `legacy` and `self_hosted_code` unchanged until the new backend passes live acceptance.

**TDD rule:** Write schema and invariant tests before models, executor tests before provider integration, deterministic pipeline tests before worker wiring, and Playwright tests before enabling the experiment flag.

## Product decisions and invariants

1. The first LLM call produces the canonical question-and-solution JSON. The DOCX agent may arrange and style that content but must not silently change assessed meaning, correct answers, equations, or source mappings.
2. Gemini authors the document by selecting and configuring tools. Trusted code performs low-level OOXML serialization.
3. The new backend never executes LLM-authored Python, shell commands, macros, arbitrary XML, or filesystem paths.
4. Visible assessed content is resolved from immutable `content_ref` and `equation_id` values. The model does not copy equation JSON or answer-key text into a second manifest.
5. The canonical assessment version uses a validated clone of version 1 assessment JSON. A separate layout manifest records document structure and evidence; it is not an independently authored assessment.
6. The compiler generates the answer key, source mapping, equation mapping, and artifact manifest from the same content catalog used to render the DOCX.
7. Machine failures cannot be overridden by the LLM. LLM approval is necessary but not sufficient for canonicalization.
8. Revision is bounded. Default to one initial design plus at most two visual revision turns. No unbounded AFC loop is allowed.
9. Every tool action is idempotent, ordered, persisted, hash-linked, and replayable.
10. On terminal failure, version 1 and its legacy artifact remain immutable and available as original recovery. Do not silently fall back and label the legacy file as an LLM-authored rewrite.

## End-to-end flow

```text
Assessment LLM
  -> validated immutable question/solution JSON (version 1)
  -> content catalog and equation registry
  -> Gemini DOCX design turn
  -> typed DOCX tool actions
  -> trusted document workspace executor
  -> draft DOCX + compiler-generated layout manifest
  -> LibreOffice PDF + bounded page PNGs
  -> package/semantic/render validators
  -> Gemini visual review
       -> approved: canonicalize version 2 and artifact
       -> revise: targeted tool actions, render again
       -> reject/budget exhausted: rewrite_failed and original recovery
```

The trusted executor runs inside the controlled DOCX service environment during every tool batch. There is no final step that runs generated Python.

## Proposed files

### New backend schemas and persistence

- Add `backend/schemas/docx_tool_schema.py`
- Add `backend/models/docx_tool_session.py`
- Add `backend/migrations/versions/20260803_01_agentic_docx_tools.py`
- Modify `backend/models/__init__.py`
- Modify `backend/models/model_call_usage.py`
- Modify `backend/models/run.py`

### Content catalog, workspace, compiler, and rendering

- Add `backend/services/docx_content_catalog.py`
- Add `backend/services/docx_tool_workspace.py`
- Add `backend/services/docx_tool_executor.py`
- Add `backend/services/docx_layout_manifest.py`
- Add `backend/services/docx_visual_renderer.py`
- Add `backend/services/docx_visual_review.py`
- Reuse `backend/services/omml.py`
- Reuse and extend `backend/services/docx_package_verifier.py`
- Reuse and extend `backend/services/docx_render_verifier.py`

### Gemini agent and orchestration

- Add `backend/services/gemini_docx_tool_agent.py`
- Add `backend/services/agentic_docx_pipeline.py`
- Add `backend/prompts/docx_tool_design_system.md`
- Add `backend/prompts/docx_tool_visual_review.md`
- Modify `backend/services/llm_client.py`
- Modify `backend/services/usage_tracking.py`
- Modify `backend/workers/assessment_worker.py`
- Modify `backend/config.py`

### API, UI, evidence, and operations

- Modify `backend/schemas/run_schema.py`
- Modify `backend/api/runs.py`
- Add `backend/scripts/run_agentic_docx_experiment.py`
- Modify `frontend/src/types/index.ts`
- Modify `frontend/src/pages/ProgressPage.tsx`
- Modify `frontend/src/pages/AssessmentViewerPage.tsx`
- Modify `frontend/src/components/TokenUsage.tsx`
- Modify `frontend/e2e/run-lifecycle.spec.ts`
- Add `docs/operations/agentic-docx-tools.md`
- Modify `.env.example`

## Task 1: Define the immutable content catalog

### 1. Write failing catalog tests

Add `backend/tests/test_docx_content_catalog.py`. Assert that the catalog:

- is deterministically derived from version 1 parsed JSON;
- assigns stable references for metadata, question bodies, options, solution fields, revision options, and traceability;
- indexes every equation by `(question_id, equation_id)` and preserves its `math`, `expression`, and `location` data;
- rejects duplicate question IDs, duplicate equation IDs, dangling `[[EQ:...]]` references, missing correct-answer data, and hash drift;
- exposes no mutable ORM objects;
- has stable canonical bytes and SHA-256;
- supports short-answer and multiple-choice questions without assuming five options for every assessment type.

Suggested references:

```text
assessment.metadata.course
question.20.title
question.20.body
question.20.option.A.body
question.20.solution.step.0
question.20.solution.physical_meaning
equation.20.mu_jt_def_q
```

### 2. Implement the catalog

The catalog owns all assessed content. Tool arguments reference catalog IDs rather than repeating assessed strings. Allow bounded decorative text only for non-assessed headings or callouts, and mark it separately in the layout manifest.

Expose methods such as:

```python
catalog.resolve_text(content_ref)
catalog.resolve_question(question_id)
catalog.resolve_equation(question_id, equation_id)
catalog.question_ids
catalog.sha256
```

### 3. Verify

```powershell
pytest backend/tests/test_docx_content_catalog.py backend/tests/test_equation_label_contract.py -q
```

## Task 2: Define the typed DOCX tool protocol

### 1. Write failing schema tests

Add `backend/tests/test_docx_tool_schema.py`. Define discriminated Pydantic models for a bounded tool vocabulary:

- `create_document`
- `set_page_layout`
- `set_theme`
- `set_header_footer`
- `add_section`
- `add_heading`
- `add_content`
- `add_question`
- `add_equation`
- `add_solution`
- `add_answer_key`
- `add_quality_check`
- `add_callout`
- `add_table`
- `add_page_break`
- `move_block`
- `update_block_style`
- `remove_decorative_block`
- `finalize_document`

Reject unknown tools, unknown style tokens, arbitrary paths, arbitrary XML, code fields, unsupported URLs, raw equation XML, and unbounded literal text.

Every mutating call must include:

```json
{
  "operation_id": "design-1-op-004",
  "tool": "add_equation",
  "expected_workspace_revision": 3,
  "arguments": {
    "block_id": "q20-eq-definition",
    "parent_id": "question-20",
    "question_id": "20",
    "equation_id": "mu_jt_def_q",
    "alignment": "center"
  }
}
```

### 2. Define stable style tokens

The model selects tokens rather than raw OOXML values. Initial tokens should cover:

- page size, margins, orientation, and section breaks;
- approved fonts, sizes, spacing, colors, borders, and shading;
- paragraph, heading, equation, question-card, table, callout, and solution-step variants;
- accessibility properties such as heading level, table headers, alt text, and keep-with-next.

Raw numeric overrides must have strict ranges. Unknown tokens fail before workspace mutation.

### 3. Define design and revision responses

`DocxDesignTurn` contains an ordered operation batch plus a concise rationale. `DocxReviewTurn` contains:

```json
{
  "decision": "approve | revise | reject",
  "observations": [],
  "operations": []
}
```

An `approve` response must contain no mutating operations. A `revise` response must contain at least one valid operation. A `reject` response terminates the cycle without canonicalization.

### 4. Verify

```powershell
pytest backend/tests/test_docx_tool_schema.py -q
```

## Task 3: Persist replayable tool sessions and iterations

### 1. Write migration and model tests

Add:

- `DocxToolSession`: run, source assessment, cycle number, provider/model, status, content-catalog hash, design-contract hash, workspace revision, initial/final workspace hash, maximum revisions, final decision, timestamps, and idempotency key.
- `DocxToolIteration`: session, iteration number, kind (`design` or `visual_revision`), model-call usage, input workspace hash, output workspace hash, draft DOCX/PDF hashes, page-image metadata, validator report, review decision, and timestamps.
- `DocxToolAction`: iteration, sequence number, operation ID, tool name, validated arguments, status, safe error code, before/after workspace hashes, and duration.

Do not persist page-image bytes, raw provider prompts, secrets, or unrestricted model reasoning. Persist image hashes, dimensions, and temporary-storage handles only for the bounded review lifetime.

Add database constraints for:

- unique `(run_id, cycle_number)` sessions;
- unique session idempotency key;
- unique `(session_id, iteration_number)`;
- unique operation IDs per session;
- contiguous action sequences;
- bounded iteration numbers;
- one model-call usage row per design/review iteration;
- valid lifecycle transitions.

### 2. Extend model-call stages

Add stages:

- `docx_tool_design`
- `docx_visual_review`

Retain `docx_code_generation` and `docx_code_repair` for historical `self_hosted_code` evidence. Never relabel old usage.

### 3. Rehearse migration

The migration must add tables and expand check constraints without rewriting existing attempts. Verify all historical runs and canonical pointers remain unchanged.

```powershell
pytest backend/tests/test_agentic_docx_models.py backend/tests/test_migrations.py -q
python -m alembic upgrade head
python -m alembic current
```

## Task 4: Implement the stateful document workspace

### 1. Write failing workspace tests

Add `backend/tests/test_docx_tool_workspace.py`. Assert:

- workspace creation is deterministic;
- every block has a stable ID and parent;
- revision numbers increase once per successful operation;
- stale expected revisions fail without mutation;
- duplicate operation IDs return the original result;
- block moves cannot create cycles;
- assessed blocks cannot be deleted or replaced by decorative literals;
- required sections and every source question remain represented exactly once;
- workspace serialization and replay produce identical hashes.

### 2. Implement a document intermediate representation

The workspace should store a typed block tree, not a mutable `python-docx` object between model turns. Example:

```json
{
  "revision": 8,
  "theme": "academic_blue",
  "blocks": [
    {
      "id": "question-20",
      "type": "question",
      "question_id": "20",
      "style": "numbered_card",
      "children": [
        {"id": "q20-body", "type": "content", "content_ref": "question.20.body"},
        {"id": "q20-eq", "type": "equation", "question_id": "20", "equation_id": "mu_jt_def_q"}
      ]
    }
  ]
}
```

This IR is the replayable source of truth. Compile a fresh DOCX after each accepted operation batch.

### 3. Add transaction semantics

Validate an entire model operation batch against a cloned workspace. Commit the batch only if every operation succeeds and the resulting workspace satisfies structural invariants. A failed batch must leave the previous revision unchanged.

### 4. Verify

```powershell
pytest backend/tests/test_docx_tool_workspace.py backend/tests/test_docx_tool_executor.py -q
```

## Task 5: Build the trusted DOCX compiler

### 1. Write compiler contract tests

Add `backend/tests/test_agentic_docx_compiler.py`. Compile deterministic fixtures for:

- short-answer and MCQ assessments;
- inline and display equations;
- metadata, question, solution, answer-key, quality-check, and revision sections;
- tables that span pages;
- headers, footers, page numbers, and section breaks;
- accessible heading levels and repeated table headers;
- long content, Unicode, and special characters.

### 2. Reuse the existing equation implementation

Resolve equations directly from the immutable equation registry and render with `backend/services/omml.py`. Gemini supplies only `question_id`, `equation_id`, placement, and an approved style token.

Test that:

- every equation reference becomes editable OMML;
- equations are never reconstructed from model text;
- no raw LaTeX, MathML, image fallback, or duplicated expression appears;
- question/solution locations remain correct;
- missing or duplicate equation placement is a machine validation error.

### 3. Generate the manifest from compiler inputs

The compiler must produce two related artifacts:

1. A cloned, validated assessment JSON for canonical version 2. It preserves question IDs, answers, solutions, equations, and traceability from version 1.
2. A layout manifest containing workspace hash, catalog hash, block-to-content mappings, equation placements, style tokens, tool-session ID, iteration number, DOCX hash, render hashes, and validator versions.

Do not ask Gemini to produce an answer key or source mapping independently. Generate both from the catalog.

### 4. Verify package safety

Run existing package checks and add compiler-specific assertions for no macros, OLE, ActiveX, external relationships, or unapproved embedded parts.

```powershell
pytest backend/tests/test_agentic_docx_compiler.py backend/tests/test_docx_package_verifier.py backend/tests/test_docx_manifest_verifier.py -q
```

## Task 6: Render drafts to PDF and bounded page images

### 1. Write renderer tests

Add `backend/tests/test_docx_visual_renderer.py`. The renderer must:

- invoke the pinned LibreOffice command with a clean temporary user profile;
- produce PDF deterministically enough for evidence while comparing semantic/page evidence rather than raw PDF bytes when metadata varies;
- render each PDF page to PNG using a pinned library or binary;
- enforce maximum pages, dimensions, per-image bytes, total review bytes, and timeout;
- return page number, width, height, PNG hash, and temporary handle;
- clean up all temporary content after the review lifetime;
- never expose arbitrary local paths to Gemini.

### 2. Add machine visual checks

Before calling Gemini, calculate safe structured findings for:

- blank pages;
- unexpectedly sparse pages;
- clipping or content outside page bounds where measurable;
- isolated headings;
- table overflow indicators;
- missing required headings;
- suspicious page-count changes;
- missing OMML and missing catalog content.

Machine checks remain authoritative. Gemini review cannot dismiss a fatal finding.

### 3. Verify

```powershell
pytest backend/tests/test_docx_visual_renderer.py backend/tests/test_docx_render_verifier.py -q
```

## Task 7: Implement the Gemini DOCX tool agent

### 1. Write provider tests with a fake Gemini client

Add `backend/tests/test_gemini_docx_tool_agent.py`. Assert:

- the initial design turn receives the catalog index, design contract, tool declarations, required sections, and current empty workspace;
- assessed strings are represented as references rather than duplicated into tool arguments;
- revision turns receive the current workspace, validator findings, bounded page images, and previous decisions;
- tool batches validate before execution;
- provider prose, code, Markdown, unknown tools, stale revisions, oversized batches, and invalid decisions are rejected;
- model usage and provider response IDs are recorded exactly once;
- no automatic model substitution or token-threshold fallback occurs.

### 2. Implement manual bounded tool orchestration

Do not enable unrestricted automatic function calling. The application controls each model turn:

1. send declared tools and context;
2. collect one bounded operation batch;
3. validate and execute locally;
4. compile and render;
5. send one explicit review turn;
6. repeat only while budget remains.

Set hard limits for operations per batch, tool-argument bytes, images, pages, model turns, and total wall time.

### 3. Send page images safely

Use Gemini inline image parts with bounded PNG bytes. Do not upload the DOCX, database records, service tokens, local paths, sandbox logs, or unrelated pages. The review prompt must distinguish machine findings from visual suggestions.

### 4. Record separate usage stages

Initial design uses `docx_tool_design`, attempt 1. Each review turn uses `docx_visual_review`, with attempt equal to its one-based review iteration. Display these separately in the UI and token experiment.

### 5. Verify

```powershell
pytest backend/tests/test_gemini_docx_tool_agent.py backend/tests/test_usage_tracking.py -q
```

## Task 8: Implement the bounded agentic pipeline

### 1. Write deterministic pipeline tests

Add `backend/tests/test_agentic_docx_pipeline.py` for:

1. initial design passes machine validation and Gemini approves;
2. first render receives targeted revisions and second render is approved;
3. stale or invalid revision batch rolls back without corrupting the workspace;
4. machine-fatal output cannot be approved;
5. review budget exhaustion produces `rewrite_failed`;
6. provider transport failure remains resumable and idempotent;
7. worker redelivery does not duplicate actions or model usage;
8. version 1 remains immutable on every failure;
9. successful canonicalization atomically persists version 2, artifact, session evidence, and pointer;
10. export resolves only to the verified canonical artifact.

### 2. Define lifecycle mapping

Reuse user-visible states while giving them tool-specific messages:

```text
docx_authoring  -> Gemini is designing the Word document
docx_executing  -> Applying document operations
docx_validating -> Rendering and verifying the Word document
docx_repairing  -> Gemini is revising the rendered document
complete        -> Verified canonical document available
rewrite_failed  -> Original document remains available
```

Persist the internal session/iteration state separately; do not derive resumability from the display message.

### 3. Define approval rules

Canonicalize only when all conditions hold:

- every operation and workspace invariant passes;
- package, semantic, equation, and render validators have no fatal issue;
- all immutable questions and solutions are represented exactly once;
- layout and artifact manifests match the compiled DOCX hash;
- Gemini review decision is `approve`;
- iteration and resource budgets are not exceeded.

### 4. Verify

```powershell
pytest backend/tests/test_agentic_docx_pipeline.py backend/tests/test_assessment_versions.py -q
```

## Task 9: Integrate configuration and worker dispatch

### 1. Extend configuration safely

Add:

```env
DOCX_GENERATION_BACKEND=legacy
DOCX_TOOL_MAX_REVISIONS=2
DOCX_TOOL_MAX_OPERATIONS_PER_TURN=100
DOCX_TOOL_MAX_REVIEW_PAGES=25
DOCX_TOOL_MAX_REVIEW_IMAGE_BYTES=20971520
DOCX_TOOL_MAX_TOTAL_SECONDS=180
```

`legacy` remains the default. `self_hosted_code` remains available only for historical experiment comparison. `agentic_tools` is enabled explicitly.

### 2. Route in the worker

Refactor `_create_document` into backend-specific adapters rather than adding another large conditional:

```python
generator = document_generator_registry.get(settings.docx_generation_backend)
result = generator.generate(db=db, run=run, attachments=attachments, progress=progress)
```

Adapters:

- `LegacyDocumentGenerator`
- `SelfHostedCodeDocumentGenerator`
- `AgenticToolDocumentGenerator`

All adapters return one common result type, but only the agentic adapter owns tool sessions.

### 3. Preserve retries and idempotency

Provider/network failures may use Celery transport retries without consuming a new design iteration. A new model turn occurs only when no persisted successful provider response exists for that iteration.

### 4. Verify

```powershell
pytest backend/tests/test_assessment_worker.py backend/tests/test_worker.py backend/tests/test_agentic_docx_pipeline.py -q
```

## Task 10: Expose agentic progress, evidence, and token usage

### 1. Extend API response tests

Expose safe fields:

```json
{
  "rewrite": {
    "backend": "agentic_tools",
    "status": "in_progress",
    "iteration": 1,
    "maximum_revisions": 2,
    "workspace_revision": 14,
    "displaying": "original"
  },
  "token_usage": {
    "stages": [
      {"stage": "docx_tool_design", "model_calls": 1},
      {"stage": "docx_visual_review", "model_calls": 1}
    ]
  }
}
```

Never expose tool arguments containing decorative text, page images, temporary handles, raw prompts, internal workspace JSON, sandbox output, or secrets through the normal run API.

### 2. Update progress UI

Show:

- designing document;
- applying document operations;
- rendering draft;
- reviewing pages;
- revising draft `n` of `max`;
- verified canonical document;
- terminal recovery with safe issue codes.

The viewer must clearly label version 2 as `Canonical LLM-designed document` and version 1 as `Original recovery document`.

### 3. Update the evidence script

Extend or add an experiment script that reports:

- design and review token usage;
- number and names of tools used, without raw arguments;
- workspace revisions and hashes;
- render count, durations, page counts, and image hashes;
- validator results;
- final review decision;
- artifact hash and size;
- whether the revision budget was used.

### 4. Verify

```powershell
pytest backend/tests/test_api_runs.py backend/tests/test_agentic_docx_token_experiment.py -q
npm --prefix frontend test -- --run
```

## Task 11: Add end-to-end and visual acceptance scenarios

### 1. Add deterministic Playwright fixtures

Cover:

1. design approved on first render;
2. one visual revision followed by approval;
3. machine-fatal output that Gemini attempts to approve;
4. exhausted revision budget with original recovery;
5. stage-specific token updates;
6. successful canonical download;
7. page images and internal tool arguments absent from public responses.

### 2. Run a live Gemini experiment

Use one representative, policy-approved assessment containing:

- at least one short-answer or computational question;
- multiple native equations;
- a long solution;
- answer-key and quality-check tables;
- enough content to span multiple pages.

Record the run ID, model version, migration revision, application revision, renderer version, tool schema version, design-contract hash, artifact hash, stage tokens, operations summary, and page-by-page evidence.

### 3. Require page-by-page human acceptance

Gemini visual approval is not a substitute for rollout acceptance. For the first live artifact, inspect every rendered page for clipping, hierarchy, typography, table wrapping, equations, headers, footers, page breaks, and accessibility. Record deviations and approval explicitly.

### 4. Verify

```powershell
npm --prefix frontend run build
npm --prefix frontend exec playwright test frontend/e2e/run-lifecycle.spec.ts
```

## Task 12: Rollout, comparison, and rollback

### 1. Keep all three backends explicit

Run controlled comparisons across:

- `legacy`: deterministic baseline;
- `self_hosted_code`: historical full-code experiment;
- `agentic_tools`: proposed LLM tool workflow.

Compare completion rate, total tokens, latency, revision count, page quality, equation correctness, manifest consistency, and human preference. Do not automatically select a backend based on token count.

### 2. Enable only after acceptance

Required gates:

- migration rehearsal passes;
- DOCX-focused and sandbox test suites pass;
- hostile tool-argument corpus passes;
- one live agentic run canonicalizes successfully;
- every equation is editable OMML;
- page-by-page human review passes;
- original recovery is proven;
- token and tool evidence is complete;
- no arbitrary model code is executed.

### 3. Roll back safely

Rollback changes only `DOCX_GENERATION_BACKEND` to `legacy`. Preserve tool sessions, actions, model usage, layout manifests, render hashes, successful canonical artifacts, and failure evidence. Do not downgrade the database while agentic evidence exists.

## Final verification matrix

Run before declaring Plan 5 complete:

```powershell
python -m alembic current
pytest backend/tests/test_docx_content_catalog.py backend/tests/test_docx_tool_schema.py backend/tests/test_agentic_docx_models.py -q
pytest backend/tests/test_docx_tool_workspace.py backend/tests/test_docx_tool_executor.py backend/tests/test_agentic_docx_compiler.py -q
pytest backend/tests/test_docx_visual_renderer.py backend/tests/test_gemini_docx_tool_agent.py backend/tests/test_agentic_docx_pipeline.py -q
pytest backend/tests/test_api_runs.py backend/tests/test_assessment_worker.py backend/tests/test_usage_tracking.py -q
pytest docx_sandbox/tests -q
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend exec playwright test frontend/e2e/run-lifecycle.spec.ts
```

Then run one approved live experiment and save its content-free evidence report. Plan 5 is incomplete until the live run produces a verified canonical DOCX and the page-by-page human acceptance record is complete.
