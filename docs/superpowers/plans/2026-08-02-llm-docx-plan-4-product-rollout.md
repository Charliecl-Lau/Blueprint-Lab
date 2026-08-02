# Plan 4: API, Viewer, Token Experiment, and Rollout

**Goal:** Expose the versioned rewrite lifecycle safely to the UI, let the user manually inspect token usage and retry a failed rewrite, and deploy the self-hosted experiment with end-to-end and visual acceptance evidence.

**Depends on:** Plans 1, 2, and 3.

**Architecture:** API responses identify original and canonical versions explicitly. Progress UI mirrors persisted worker states. The viewer shows the canonical rewrite after success and the original recovery version after `rewrite_failed`. Each authoring cycle has one initial attempt and at most one repair; an explicit rewrite-only retry starts a new immutable cycle and never selects Option B automatically.

**TDD rule:** Add backend API tests before endpoint changes, component/store tests before UI changes, and Playwright scenarios before declaring rollout complete.

## Proposed files

- Modify `backend/schemas/run_schema.py`
- Modify `backend/api/runs.py`
- Modify `backend/services/run_service.py`
- Add `backend/services/docx_rewrite_retry_service.py`
- Modify `backend/tests/test_api_runs.py`
- Modify `backend/tests/test_run_progress.py`
- Add `backend/tests/test_docx_rewrite_retry.py`
- Modify `frontend/src/types/index.ts`
- Modify `frontend/src/api/runs.ts`
- Modify `frontend/src/store/runStore.ts`
- Modify `frontend/src/pages/ProgressPage.tsx`
- Modify `frontend/src/pages/AssessmentViewerPage.tsx`
- Modify `frontend/src/components/TokenUsage.tsx`
- Add or modify matching Vitest files
- Modify `frontend/e2e/run-lifecycle.spec.ts`
- Add `backend/scripts/run_docx_token_experiment.py`
- Add `docs/operations/docx-authoring-experiment.md`
- Modify `.env.example`
- Add sandbox deployment configuration appropriate to the existing platform

## Task 1: Expose explicit version and rewrite state in the API

### 1. Write failing response-contract tests

`GET /runs/{id}` must expose:

```json
{
  "status": "complete",
  "rewrite": {
    "status": "succeeded",
    "attempt_count": 1,
    "repair_available": false,
    "original_assessment_id": 41,
    "original_version": 1,
    "canonical_assessment_id": 42,
    "canonical_version": 2,
    "displaying": "canonical_rewrite",
    "artifact_available": true
  }
}
```

For `rewrite_failed`, assert `displaying == "original_recovery"`, canonical version is still 1, artifact is unavailable, and failure contains safe issue codes—not source code, document bytes, raw logs, or service secrets.

Token usage must include distinct `docx_code_generation` and `docx_code_repair` stages when present. `recording_state` becomes terminal for `rewrite_failed`.

### 2. Implement serializers against explicit relationships

Never use `max(version)` to choose displayed content. Read `run.canonical_assessment_id`, and derive original version by kind. Keep a legacy compatibility shape only if current frontend tests require it; document its removal path.

Update statuses in `RunSummary`, `RunDetail`, recent runs, SSE snapshots, and terminal-status helpers:

```python
ACTIVE_REWRITE_STATUSES = {
    "docx_authoring", "docx_executing", "docx_validating", "docx_repairing"
}
TERMINAL_STATUSES = {
    "complete", "complete_with_warnings", "rewrite_failed", "error"
}
```

Run:

```powershell
pytest backend/tests/test_api_runs.py backend/tests/test_run_progress.py backend/tests/test_usage_tracking.py -q
```

### 3. Commit checkpoint

```text
Expose canonical rewrite state and stage usage

This makes assessment versions, recovery display state, artifact readiness,
repair availability, and DOCX-stage tokens explicit in run responses and SSE
snapshots without exposing generated code or sandbox logs.
```

## Task 2: Add the explicit rewrite-only retry endpoint

### 1. Write failing authorization and idempotency tests

Test `POST /runs/{id}/docx-rewrite/retry`:

- returns `404` for an unknown run;
- returns `409` unless the run is `rewrite_failed` with a valid immutable original assessment;
- starts the next authoring cycle with a fresh initial attempt and at most one repair;
- uses an idempotency key so duplicate submits queue only one new cycle;
- does not create a new experiment run or mutate version 1;
- does not switch to Option B;
- allows an operator to retry after a security-policy rejection only as a wholly new cycle; the rejected program itself is never repaired or executed again;
- returns the updated run snapshot.

### 2. Implement a narrow service operation

```python
def request_docx_rewrite(db: Session, run_id: int, idempotency_key: str) -> Run:
    run = lock_run(db, run_id)
    require_rewrite_failed_with_original(run)
    cycle_number = next_cycle_number(run)
    reserve_rewrite_cycle(run.id, cycle_number, idempotency_key)
    enqueue_docx_rewrite(run.id, cycle_number, idempotency_key)
    run.status = "docx_authoring"
    run.progress_message = "Retrying the Word document rewrite"
    db.commit()
    return run
```

The new cycle receives the same full grounding from immutable application data. It does not treat the prior cycle's failed program as its repair input. Within the new cycle, Plan 3 still permits exactly one bounded repair. Rate limits and operator authorization may restrict repeated cycles, but the system does not overwrite or silently discard their evidence.

Run:

```powershell
pytest backend/tests/test_docx_rewrite_retry.py backend/tests/test_api_runs.py -q
```

### 3. Commit checkpoint

```text
Add an explicit bounded DOCX rewrite retry

This endpoint starts a new immutable authoring cycle for a failed rewrite with
locking and idempotency. Each cycle still permits only one repair, and retry
never creates a new run or invokes the preserved future Option B workflow.
```

## Task 3: Update frontend types, store, and progress UI

### 1. Write failing TypeScript and component tests

Extend `Stage` and run types. Test that:

- each authoring state has a clear label;
- active rewrite states continue polling/SSE;
- `rewrite_failed` is terminal;
- a failure page offers recovery viewing and, only when allowed, one repair action;
- token totals update after the authoring and repair calls;
- no UI says the backend itself composed the DOCX.

Suggested labels:

```typescript
const labels: Record<Stage, string> = {
  pending: 'Queued',
  prompting: 'Writing prompt',
  generating: 'Generating assessment JSON',
  docx_authoring: 'Authoring Word document',
  docx_executing: 'Building Word document in sandbox',
  docx_validating: 'Verifying Word document',
  docx_repairing: 'Repairing Word document',
  rewrite_failed: 'Word rewrite failed',
  documenting: 'Preparing legacy document',
  complete: 'Complete',
  complete_with_warnings: 'Complete with warnings',
  error: 'Error',
}
```

### 2. Implement store and progress behavior

Add a single terminal-status helper shared by polling behavior. Render persisted `progress_message` as supplemental detail. On failure, link to the viewer rather than hiding the original assessment.

Run:

```powershell
Set-Location frontend
npm test -- --run src/store/runStore.test.ts src/pages/ProgressPage.test.tsx src/components/TokenUsage.test.tsx
```

### 3. Commit checkpoint

```text
Show DOCX authoring and repair progress

This updates frontend state handling for the new persisted lifecycle and keeps
the original assessment reachable after a failed rewrite. Stage-level tokens
remain visible for manual experiment monitoring.
```

## Task 4: Make the viewer version-aware

### 1. Write failing viewer tests

Success case:

- renders version 2 manifest content;
- shows `Canonical LLM rewrite` and source version metadata;
- enables DOCX export only when verified artifact exists;
- grading and evaluation IDs point to version 2.

Failure case:

- renders version 1 original JSON;
- shows `Original assessment — DOCX rewrite failed` recovery banner;
- disables DOCX export and rewrite grading;
- shows safe failure summary and repair button only when available;
- does not mix version 1 evaluations with a version 2 label.

Step-by-step solution test:

```tsx
expect(screen.getByText('Knowns and target')).toBeVisible()
expect(screen.getByText('Governing equation')).toBeVisible()
expect(screen.getByText('Substitution')).toBeVisible()
expect(screen.getByText('Final answer')).toBeVisible()
expect(screen.getByText('Physical meaning')).toBeVisible()
expect(screen.getByText('Distractor analysis')).toBeVisible()
```

Conceptual questions assert governing concept, application, option elimination, and conclusion instead.

### 2. Implement typed solution rendering

Do not render the manifest as arbitrary HTML. Map typed fields to existing `MathContent` and accessible semantic components. Keep the export URL attached to the verified canonical artifact only.

Run:

```powershell
Set-Location frontend
npm test -- --run src/pages/AssessmentViewerPage.test.tsx src/api/runs.test.ts src/store/runStore.test.ts
```

### 3. Commit checkpoint

```text
Render canonical rewrites and original recovery versions

This makes assessment provenance visible and renders the typed step-by-step
solution contract. Export and grading are enabled only for the verified
canonical rewrite, while failed runs retain a clearly labeled original view.
```

## Task 5: Add the manual token-usage experiment runner

### 1. Write failing script/service tests

The opt-in experiment command accepts explicit run IDs or creates a deliberately specified run. It outputs machine-readable JSON/CSV with:

- run and condition identifiers;
- provider/model/model version for every call;
- input, output, cached, reasoning, and total tokens by stage and attempt;
- total end-to-end model tokens;
- authoring and repair durations;
- sandbox execution and render durations separately;
- grounding byte/hash information;
- DOCX byte size, page count, and validation outcome;
- whether repair was used.

It must not include source content, prompt text, generated code, or secrets. It must never auto-change models, select Option B, or decide whether token usage is acceptable.

Example output:

```json
{
  "run_id": 123,
  "model": "gemini-3.5-flash-lite",
  "stages": {
    "assessment": {"input_tokens": 12000, "output_tokens": 8000},
    "docx_code_generation": {"input_tokens": 25000, "output_tokens": 14000}
  },
  "repair_used": false,
  "decision": null
}
```

### 2. Implement as an explicit operator tool

Require a confirmation flag for live model calls, such as `--execute-live`. Default mode reads already persisted runs. Write reports to an explicit operator-supplied path and redact logs.

Run:

```powershell
pytest backend/tests/test_docx_token_experiment.py -q
python -m backend.scripts.run_docx_token_experiment --run-id 123
```

### 3. Commit checkpoint

```text
Report DOCX experiment tokens without automatic decisions

This adds an opt-in, redacted report of model tokens and non-model execution
timings by stage. It supplies the evidence for manual workflow evaluation while
leaving fallback and redesign decisions entirely to the operator.
```

## Task 6: Add end-to-end tests and deployment controls

### 1. Write Playwright scenarios before rollout

Use deterministic backend fixtures for:

1. authoring success without repair;
2. first failure followed by repair success;
3. terminal `rewrite_failed` with original recovery view;
4. stage-token updates;
5. verified DOCX download;
6. no artifact or grading access before canonicalization.

Run:

```powershell
Set-Location frontend
npm test -- --run
npm run build
npx playwright test e2e/run-lifecycle.spec.ts
```

### 2. Add deployment configuration and runbook

Document and configure:

- `DOCX_GENERATION_BACKEND=legacy` as the safe default;
- `DOCX_GENERATION_BACKEND=self_hosted_code` only in the experiment environment;
- private sandbox URL and authentication;
- immutable service and job image digests;
- resource, timeout, concurrency, retention, and health settings;
- pinned LibreOffice, fonts, locale, and Python packages;
- database migration order;
- rollback by disabling new runs while preserving all evidence;
- free-tier Gemini data-use caveat and prohibition on sensitive source material unless policy permits it.

The later OpenAI-hosted provider remains documented as a future adapter. It is not implemented in these four plans.

### 3. Run a visual acceptance experiment

For representative course material:

1. enable the flag in a non-production environment;
2. create one live run;
3. capture token report;
4. render the generated DOCX to page images;
5. inspect every page for clipping, overlap, table wrapping, equations, glyphs, figure placement, headers, footers, and page breaks;
6. compare structure with the approved design contract;
7. record pass/fail and all deviations.

This is the release visual review. Automated render smoke remains part of every production run, but the system must not claim human visual inspection per run.

### 4. Commit checkpoint

```text
Gate and verify the self-hosted DOCX experiment

This adds end-to-end lifecycle coverage, deployment controls, rollback guidance,
and a page-by-page release acceptance procedure. The new path remains disabled
by default until its security, formatting, and token evidence are reviewed.
```

## Plan 4 completion gate

```powershell
pytest backend/tests -q
Set-Location frontend
npm test -- --run
npm run build
npx playwright test
```

Also require:

- successful database migration rehearsal;
- sandbox hostile-corpus pass;
- one live Gemini 3.5 Flash-Lite run with recorded stage tokens;
- page-by-page visual acceptance evidence;
- proof that version 1 remains immutable and recoverable;
- proof that no automatic token threshold or Option B fallback exists;
- feature flag disabled by default outside the approved experiment environment.

Plan 4 is complete when the user can observe the full second-call token cost, download only a verified LLM-authored DOCX, inspect the canonical rewritten assessment, recover the original after failure, and make the workflow decision manually.
