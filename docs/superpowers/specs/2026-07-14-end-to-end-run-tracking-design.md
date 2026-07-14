# End-to-End Run Tracking Design

## Scope

This design adds end-to-end Gemini token accounting, shared logo navigation, concurrent run-safe progress and history, and complete pre-run validation to Blueprint Lab. Reference-content attachments (the original Feature 4) are explicitly excluded at the user's request. Existing source-document behavior remains unchanged unless a compatibility adjustment is required by another in-scope change.

The implementation extends the existing immutable research-run model without redesigning unrelated experiment functionality. A stable run ID is the correlation key for model calls, token usage, Celery work, progress, results, errors, and frontend state.

## Current architecture

Blueprint Lab uses FastAPI, SQLAlchemy, PostgreSQL, Alembic, Celery, Redis, React, React Router, Zustand, and the Google Gen AI SDK. Creating an experiment currently creates one condition and one pending run, then enqueues `run_generation_pipeline`. That pipeline performs two Gemini calls: actual-prompt generation and assessment generation. Redis publishes experiment-level progress, while the browser subscribes through SSE. Run records and results already persist in PostgreSQL.

The existing implementation already gives every run a database record and Celery invocation, but it has no usage-metadata persistence. Its SSE stream is experiment-scoped and event-only, so a reconnect can miss state changes. Frontend state keys runs by ID but stores only one current experiment and resets that state when creating another experiment. The shared logo is not consistently interactive. Frontend validation exists, but its dialog, accessibility behavior, inline clearing, and backend error structure are incomplete.

## Data model

### Model-call usage

Add a `model_call_usages` table with one row for each distinct Gemini call attempt. Each row contains:

- Primary key and application-generated call ID.
- Run ID foreign key.
- Generation stage, initially `actual_prompt` or `assessment`, with the same recording interface available to future planning, validation, repair, or structured-output retry stages.
- Attempt number within the stage.
- Provider response ID when Gemini supplies one.
- Safe call status, distinguishing a response with usage, a response without usage, and a transport/provider failure without a usable response.
- API-reported prompt/input token count.
- API-reported candidate/generated-output token count.
- API-reported total token count.
- API-reported cached-content and thoughts/reasoning token counts when present.
- A JSON object for additional documented provider token categories, kept separate from input and output counts.
- Creation and response timestamps.

Token fields are nullable because legacy records and failed calls may not have usage metadata. The implementation never estimates missing usage and never silently folds additional categories into input or output.

The application call ID is unique. A partial unique constraint on provider response identity, scoped appropriately for non-null response IDs, prevents the same Gemini response from being recorded twice. Each genuinely repeated provider call uses a new call ID and creates its own record.

### Run aggregates

Add nullable aggregate columns to `runs`:

- `input_tokens`
- `output_tokens`
- `total_tokens`
- `model_call_count`

Migration-created values remain null for existing runs, allowing the UI and exports to distinguish “Not recorded” from zero. Newly created runs initialize all four values to zero. Every distinct Gemini request increments `model_call_count`, including a failed attempt whose response provides no usage. When Gemini reports usage, the available token counts are added atomically to the run aggregates. The individual rows remain the auditable source of truth, and tests verify that call counts and token aggregates match those rows.

The run API also groups recorded calls by stage for an optional breakdown. Missing categories remain null rather than being presented as zero unless the provider explicitly reported zero.

## Gemini call lifecycle

`LLMClient` will normalize Gemini responses into an envelope containing raw text, request and model metadata, finish reason, and parsed SDK usage metadata. Usage parsing reads the Google Gen AI SDK's actual fields, including prompt, candidate, total, cached-content, and thoughts token fields when available.

The worker creates a call ID before invoking Gemini and persists the resulting call record before later finish-reason, parsing, or schema validation decisions. Therefore a response that is truncated or structurally unusable still contributes the usage Gemini reported. A transport or SDK exception without a response creates a safe failed-call record with null usage values; it does not invent tokens.

The recording service performs call-row insertion and aggregate updates in one database transaction. Reprocessing the same normalized response with the same call ID or provider response ID is idempotent. Celery retries resume from persisted pipeline state: an already persisted actual prompt prevents that stage from being called again, while an assessment stage that genuinely calls Gemini again creates a new call row and adds only that response's usage.

All present and future Gemini call sites associated with a run must go through the same run-aware recording boundary. The initial stages are:

1. `actual_prompt`: generation of the provider-specific Actual Prompt.
2. `assessment`: generation of the structured assessment.

If repair, validation, planning, or structured-output retry calls are added to this pipeline later, they must supply their own stage name and are automatically included in the run totals.

## Run creation and idempotency

Experiment creation accepts an `Idempotency-Key` header generated once per frontend submission attempt. PostgreSQL stores this value under a unique constraint. The creation service returns both the persisted experiment/run and whether the request created them. Only a newly created run is enqueued.

Experiment, condition, and run creation occurs in one transaction after request validation. A uniqueness race retrieves and returns the already-created record. Duplicate button clicks are also prevented in the browser by disabling the Run Experiment button while submission is pending. Invalid requests never enter the creation transaction and never enqueue Celery work.

Every accepted run retains its own run row, condition relationship, Celery task, status, error, result, progress channel, and token totals. Starting a second experiment or retry run does not update, cancel, attach to, or replace an earlier run.

## Progress and reopening runs

Add run-scoped progress publication and retrieval:

- `GET /runs/{run_id}` returns the latest persisted run state, safe error information, result metadata, token aggregates, and stage breakdown.
- `GET /runs/{run_id}/progress` first reads and emits a persisted snapshot, then subscribes to `run:{run_id}:progress` in Redis for live changes.
- `GET /runs/recent` returns active and recently completed runs in descending creation order, with a bounded configurable or fixed page size.

The existing experiment retrieval remains available. Compatibility experiment-level progress may remain for existing clients, but new frontend behavior uses the run-specific stream. The worker publishes after committing state, so a subsequent API read agrees with the event. If a run is already terminal when SSE opens, the endpoint emits that snapshot and closes cleanly. If a run finishes while no browser is connected, reopening it immediately displays its persisted terminal state and result.

Unmounting a progress component closes only its browser EventSource. There is no frontend cancellation request and no Celery revoke call. Backend work is independent of the page lifecycle.

## Frontend state and routes

Normalize frontend state into ID-keyed experiment and run maps. Remove reset-on-create behavior and avoid storing a singleton current run or experiment as the source of truth. Route parameters determine the viewed experiment and run; selected viewer state is scoped by experiment or derived locally.

The progress route becomes run-specific while retaining enough experiment context for display. Navigation after creation targets the created run. Recent-run entries link active runs to progress and completed runs to the viewer. API responses always merge into the ID-keyed store without deleting unrelated runs.

The Control Assessment landing page includes a compact recent-runs section. It shows active and recently completed runs with topic, condition/run identity, status, and an accessible reopen action. This is the minimal persistent entry point for returning to work after navigation or refresh.

## Shared header and navigation

Create a shared `AppHeader` component used by the input, progress, and viewer pages. The existing Blueprint Lab wordmark remains visually unchanged and is rendered as a React Router `Link` to `/` with the accessible label “Go to Blueprint Lab home.” It participates in normal keyboard navigation and receives a visible `:focus-visible` treatment.

Logo navigation is client-side. It does not reset stores, delete records, close backend work, or call cancellation endpoints.

On an active run's progress page, a bottom-right action area appears below the main progress content and contains:

- Supporting text: “This experiment will continue running in the background.”
- A button or link labeled “Back to Control Assessment.”

The action routes to `/`. It may close the current EventSource as a normal unmount side effect, but it leaves Celery and persisted run state untouched.

## Token display and exports

The Experiment Condition section displays:

- Input tokens
- Output tokens
- Total tokens
- Model calls

Active runs label the values as in progress or partial. Completed new runs show final totals. A run whose aggregate fields are all null displays “Not recorded,” never zero. A disclosure presents stage-level call count and token totals when recorded.

The existing Word result export includes the same run token summary. Legacy exports state “Not recorded.” Run API responses include aggregates and stage breakdowns, so existing research-data consumers receive the accounting fields without access to internal credentials or infrastructure.

## Required-field validation

Frontend and backend use the same effective rules:

### Assessment Details

- Course name: nonblank after trimming.
- Topic: nonblank after trimming.
- Learning objectives: nonblank after trimming.
- Assessment format: a supported schema value.
- Difficulty: nonblank and supported by the current schema/UI contract.
- Number of questions: integer from 1 through 50.
- Estimated student completion time: integer from 1 through 480.
- Prompt structure: a supported schema value.

### Prompt Design Factors

Disabled factors require no associated content. Each enabled factor requires nonblank content after trimming:

- Concept Bridge requires bridge content.
- Few-shot Examples requires example content.
- Reference Content requires reference text because attachment support is out of scope.
- Reasoning Guidance requires guidance content.

Frontend submission builds a complete error collection before making any request. A red modal or alert states “Complete the required fields before running the experiment” and groups every error under Assessment Details or Prompt Design Factors using user-facing labels. Controls in the list move to and focus the associated field. Invalid controls receive red styling, concise inline text, `aria-invalid`, and `aria-describedby`. Closing or acknowledging the dialog moves focus to the first invalid field. Editing a field clears its error immediately once it becomes valid, without clearing other input.

The backend returns structured HTTP 422 errors with stable field paths, section names, user-facing labels, and safe messages. Pydantic and service-level validation run before database mutation. If a later database operation fails, the transaction rolls back experiment, condition, and run creation together. No task is enqueued until after a successful commit.

## API and security boundaries

Request and response schemas add run token aggregates, stage breakdowns, safe progress state, recent-run summaries, and structured validation errors. Responses do not expose Gemini API keys, Celery task IDs, broker URLs, Redis channel implementation details, database traces, internal filesystem paths, credentials, or raw exception traces.

The application currently has no authentication boundary. This work does not invent an unrelated authentication system. Run lookup uses stable IDs and preserves the existing deployment's access model. If authentication is introduced later, run, experiment, and recent-run queries must be scoped to the authenticated owner before production multi-user use.

## Reliability and compatibility

- Refresh and navigation do not affect Celery work.
- Persisted snapshots make SSE reconnect independent of missed events.
- Run-specific Redis channels and ID-keyed frontend state prevent progress and result leakage.
- Database uniqueness protects idempotent creation and one-time response accounting.
- New aggregate columns are nullable for backward compatibility.
- Existing experiments remain readable and show “Not recorded” for usage.
- Existing source-document and attachment-adjacent code is not expanded by this feature.
- Railway compatibility is preserved by using the existing PostgreSQL, Redis, API, worker, and frontend services; no new storage service is introduced.

## Testing strategy

Backend tests mock Google Gen AI responses and cover:

- Usage metadata field parsing, including cached and thoughts tokens.
- Aggregation across the two generation stages and multiple retries.
- Deduplication of repeated persistence for one response.
- Responses without usage and failures without responses.
- Truncated or invalid responses that still report usage.
- Concurrent run isolation and run-scoped progress snapshots.
- Active/recent-run retrieval and terminal reconnect behavior.
- Idempotent creation and single task enqueue.
- Conditional required-field validation and structured errors.
- Transaction rollback with no task enqueue on failure.
- Existing run/source access behavior under the current single-user access model.
- Alembic upgrade and legacy null-token behavior.

Frontend tests cover:

- Shared accessible logo navigation on every page.
- Bottom-right Back to Control Assessment placement and routing.
- EventSource cleanup without cancellation behavior.
- Reopening active and completed runs from recent history.
- Starting a second run without clearing the first.
- Partial, completed, stage-level, and legacy token displays.
- Red grouped validation dialog, all missing labels, focus movement, ARIA wiring, and inline clearing.
- Disabled submission during the creation request and reuse of one idempotency key for retries of that submission.

End-to-end component/API workflow tests use mocked Gemini and Celery boundaries to cover two independently progressing runs, leaving and reopening the first run, isolated results and token totals, and an invalid submission that creates no run and enqueues no task. Feature 4's PDF attachment step is omitted because Feature 4 was removed.

Verification includes the complete pytest suite, Alembic checks and migration tests, Vitest, frontend lint and production build, and backend/frontend/worker Docker builds when the environment supports Docker.

## Documentation

Update `README.md` with setup changes, migrations, environment variables, concurrent-run behavior, reopening runs, and validation rules.

Add `docs/RUN_LIFECYCLE_AND_TOKEN_ACCOUNTING.md` with detailed accounting definitions, included Gemini calls, retry and failure treatment, stage breakdowns, legacy behavior, idempotent creation, and run-specific progress lifecycle.

The technical design is stored at `docs/superpowers/specs/2026-07-14-end-to-end-run-tracking-design.md`. The subsequent implementation plan will be stored at `docs/superpowers/plans/2026-07-14-end-to-end-run-tracking.md`.

No PDF, upload-limit, object-storage, or attachment documentation is added because Feature 4 is excluded.

## Migration and configuration

Create a forward Alembic migration that adds `model_call_usages`, run aggregate columns, idempotency persistence, indexes, foreign keys, checks, and uniqueness constraints. Existing run aggregates remain null. New runs initialize them in application code.

No new object-storage variables are introduced. Any new configuration is limited to bounded recent-run behavior or progress timing only if implementation proves it necessary; fixed safe defaults are preferred to avoid unnecessary deployment settings.
