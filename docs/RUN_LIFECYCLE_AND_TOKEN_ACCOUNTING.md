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

Every distinct run-associated Gemini request counts as one model call. This includes Actual Prompt generation, assessment generation, assessment-quality evaluation, retries after a truncated or rejected response, repair, validation, and structured-output retries.

Responses with usage count even if the application later rejects the content or retries it. A provider failure without a response still has a call record, but its token fields remain null. A response without usage metadata is recorded as such and does not invent token values.

Each request has a unique application call ID. Provider response IDs are also deduplicated when present. Run aggregates sum only distinct call records belonging to that run, so persisting the same call or response again cannot double count it. The per-call ledger remains the audit source; run-level input, output, total, and call-count fields are convenient summaries.

Legacy runs predate this accounting ledger and retain null aggregates. They display **Not recorded.** A new run with measured zero values is distinct from a legacy run with no recording.

Evaluation calls use the `evaluation` usage stage. The Progress and Viewer pages receive updated run snapshots through Server-Sent Events, so the Viewer may initially show generation-only usage and then increase when evaluation usage is recorded. Totals never anticipate or estimate an evaluation call that has not returned usage metadata.

## Run lifecycle and isolation

The initial valid experiment submission creates an experiment, condition, and pending run transactionally, then enqueues that run. Retrying creates a new immutable run number and never overwrites the original run's evidence. A PDF-backed retry requires a fresh set of one to three reference PDFs and records the fresh ordered filenames on the new run.

The run ID isolates all mutable workflow state:

- Celery receives and processes a specific run ID.
- Redis progress uses `run:{run_id}:progress`.
- Database status, persisted progress, results, sanitized errors, and token usage belong to that run.
- Run detail and progress endpoints load the requested run rather than whichever experiment was viewed most recently.

The progress endpoint returns persisted database state first, so refreshing or reconnecting does not depend on a missed Redis event. Terminal runs close the event stream immediately after the final snapshot. Leaving or unmounting a progress page closes only that browser's Server-Sent Events connection; it never revokes or cancels Celery work. **Recent runs** can reopen active and completed runs from persisted state while other runs continue independently.

## Viewer-ready and completion boundaries

The six user-visible stages are **Preparing Prompt**, **Generating Assessment**, **Validating Assessment**, **Evaluating Assessment Quality**, **Saving Results**, and **Complete**.

Successful validation is the Viewer-ready boundary. At that point Blueprint Lab has stored the untouched provider response, parsed assessment, output hash, normalized immutable question versions, and content hashes. `viewer_ready_at` is recorded, the run moves to `evaluating_quality`, and the Viewer can display the question before evaluation finishes.

The evaluator receives the saved question and model answer directly. It analyzes the assessment but cannot modify it. The run becomes complete only after every saved question has a finalized LLM evaluation for rubric version `2026-07-16`, evaluation usage has been recorded when reported by the provider, and the result artifact has been saved.

If evaluation fails, the generated assessment, prompt provenance, output hash, and Viewer access remain intact. The run moves to `evaluation_failed`. `POST /assessments/{assessment_id}/evaluations/llm/retry` changes that same run back to evaluation without calling generation; already finalized question evaluations are skipped. Provider response IDs and application call IDs still enforce usage-ledger deduplication.

Legacy completed assessments without normalized evaluation records remain viewable. Their evaluation status is **Not started**, grading remains unavailable, and the same evaluation retry endpoint can explicitly backfill question and LLM evaluation records without regenerating or rewriting the legacy assessment, artifact, prompt, output hash, or `rubric_results` data.

## Rubric grading and research traceability

The Assessment Quality Rubric version is `2026-07-16`, with weights of 30%, 25%, 10%, 25%, and 10% across the five criteria. Scores are restricted to 1 through 5. A Technical Correctness and Solvability score below 3 fails the critical gate regardless of the weighted total.

LLM and human evaluations are separate normalized records. Each criterion score and its feedback are stored independently, and records carry the assessment/question version, run and experiment provenance, prompt/output references, rubric snapshot, evaluator identity or model version, timestamps, status, and revision. The local single-user reviewer identity comes from `LOCAL_REVIEWER_ID` and defaults to `local-reviewer`.

Human drafts use optimistic revisions and can be patched, finalized, or explicitly reopened. Finalization requires all five criterion scores. Reopening first preserves the finalized snapshot in revision history. Opening the collapsed LLM section records the first disclosure time and whether it occurred before human finalization. Comparison is available only for a finalized human review and is research data, not evidence that either evaluator is correct.

The grading APIs are:

```text
GET  /assessment-questions/{question_id}/grading-context
GET  /assessments/{assessment_id}/evaluations
POST /assessment-questions/{question_id}/evaluations/human
PATCH /evaluations/{evaluation_id}
POST /evaluations/{evaluation_id}/finalize
POST /evaluations/{evaluation_id}/reopen
POST /evaluations/{evaluation_id}/llm-access
GET  /assessment-questions/{question_id}/evaluation-comparison
```

## Creation safety and validation

Experiment creation requires an `Idempotency-Key`. Repeating a successful request with the same key returns the original experiment graph and does not enqueue a second task.

Course name, topic, and learning objectives must contain non-whitespace text. Question count must be an integer from 1 through 50, and estimated student completion time must be an integer from 1 through 480 minutes. Text content is required for enabled Concept Bridge, Few-shot Examples, and Reasoning Guidance factors. Enabled Reference Content instead requires one to three PDF files, with a 20 MB limit applied independently to each file. The UI advises users not to upload PDFs longer than 100 pages; page count is not enforced.

The frontend checks the same contract before making the API request and reports all missing fields in visual order. The backend remains authoritative and validates transactionally. An invalid submission creates no experiment, condition, run, or Celery task.

Experiment creation uses multipart form data with JSON in `payload` and ordered files in repeated `reference_pdfs` fields. The application uploads validated PDFs temporarily to Gemini Files and passes provider attachment metadata through Celery without storing it in PostgreSQL. Only ordered original filenames are persisted with the run. PDF bytes, extracted text, base64 data, provider file names, and provider URIs are not stored in the application database. Attachments are supplied only to final assessment generation and schema repair, not prompt structuring or evaluation. Automatic task retries reuse the temporary files; terminal success or failure performs best-effort deletion, with Gemini's automatic file expiration as a fallback.

## Attachment and source-document boundary

Reference Content prompt PDFs are temporary generation attachments. They do not use or change the persistent source-document subsystem, and no object storage is introduced by this workflow. Existing source-document behavior remains unchanged.
