# Run Lifecycle and Token Accounting

Blueprint Lab treats a run as the stable boundary for generation work, progress, results, errors, and model usage. This document defines what is recorded and how users can safely leave and reopen concurrent work.

## Token definitions

All token values come directly from Gemini response usage metadata. Blueprint Lab never estimates a missing value and never recomputes one category from another.

- **Input** is Gemini `prompt_token_count`.
- **Output** is Gemini `candidates_token_count`.
- **Total** is Gemini `total_token_count`. It is not calculated as input plus output.
- Cached-content tokens and thoughts/reasoning tokens remain separate categories.
- Additional API-reported token categories remain in the call record's extra counts instead of being folded into input or output.

A response can therefore have a total that differs from input plus output. A null count means the API did not report that category; it does not mean zero.

## Calls and aggregation

Every distinct run-associated Gemini request counts as one model call. This includes Actual Prompt generation, assessment generation, retries after a truncated or rejected response, repair, validation, structured-output retries, and future run-associated stages.

Responses with usage count even if the application later rejects the content or retries it. A provider failure without a response still has a call record, but its token fields remain null. A response without usage metadata is recorded as such and does not invent token values.

Each request has a unique application call ID. Provider response IDs are also deduplicated when present. Run aggregates sum only distinct call records belonging to that run, so persisting the same call or response again cannot double count it. The per-call ledger remains the audit source; run-level input, output, total, and call-count fields are convenient summaries.

Legacy runs predate this accounting ledger and retain null aggregates. They display **Not recorded.** A new run with measured zero values is distinct from a legacy run with no recording.

## Run lifecycle and isolation

The initial valid experiment submission creates an experiment, condition, and pending run transactionally, then enqueues that run. Retrying creates a new immutable run number and never overwrites the original run's evidence.

The run ID isolates all mutable workflow state:

- Celery receives and processes a specific run ID.
- Redis progress uses `run:{run_id}:progress`.
- Database status, persisted progress, results, sanitized errors, and token usage belong to that run.
- Run detail and progress endpoints load the requested run rather than whichever experiment was viewed most recently.

The progress endpoint returns persisted database state first, so refreshing or reconnecting does not depend on a missed Redis event. Terminal runs close the event stream immediately after the final snapshot. Leaving or unmounting a progress page closes only that browser's Server-Sent Events connection; it never revokes or cancels Celery work. **Recent runs** can reopen active and completed runs from persisted state while other runs continue independently.

## Creation safety and validation

Experiment creation requires an `Idempotency-Key`. Repeating a successful request with the same key returns the original experiment graph and does not enqueue a second task.

Course name, topic, and learning objectives must contain non-whitespace text. Question count must be an integer from 1 through 50, and estimated student completion time must be an integer from 1 through 480 minutes. Content is required only for prompt factors that are enabled; enabled Reference Content is satisfied by nonblank text in its field.

The frontend checks the same contract before making the API request and reports all missing fields in visual order. The backend remains authoritative and validates transactionally. An invalid submission creates no experiment, condition, run, or Celery task.

## Scope

Attachment upload, new PDF or DOCX source behavior, Gemini Files integration, object storage, and other Feature 4 behavior are not part of this change. Existing source-document functionality is unchanged.
