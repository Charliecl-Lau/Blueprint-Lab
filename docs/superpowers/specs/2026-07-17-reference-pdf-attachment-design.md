# Reference PDF Attachment Design

## Purpose

Replace the Reference Content prompt factor's free-text input with a single PDF upload. The PDF must be attached to the final Gemini assessment-generation request alongside the Actual Prompt, but its bytes and extracted text must never be stored in the application database. The database records only the original PDF filename on the corresponding run.

## Scope

This change covers the experiment wizard, experiment submission API, run persistence, Gemini temporary-file lifecycle, assessment generation and repair calls, manual run retries, validation, and automated tests.

The following are outside this change:

- Extracting PDF text into `factor_inputs`.
- Saving PDF bytes in PostgreSQL or the existing source-document subsystem.
- Enforcing a PDF page-count limit.
- Supporting multiple PDFs or non-PDF reference attachments.
- Attaching the PDF to the Anthropic prompt-structuring request.

## User Experience

Reference Content remains one of the selectable Prompt Design Factors. When it is enabled, its text area is replaced by a file selector that accepts one PDF. The interface displays the selected filename, the strict `20 MB maximum` rule, and the advisory copy `Please do not upload PDFs longer than 100 pages.`

The Review step displays the selected PDF filename. Disabling Reference Content clears the selected file and its validation error. Enabling Reference Content without selecting a PDF prevents submission and focuses the file selector through the existing grouped validation dialog.

The application strictly enforces PDF type and a 20 MB byte limit. The 100-page message is advisory only; neither the browser nor backend counts or rejects pages.

PDF-backed runs cannot use the existing one-click manual retry because their original attachment has been deleted. A manual retry asks the user to select the PDF again. Runs that did not use a reference PDF retain one-click retry behavior.

## Submission and Validation

Experiment creation changes from an application/json request to multipart form data with:

- A JSON part containing the existing experiment fields and prompt-factor configuration.
- An optional PDF part used only when Reference Content is enabled.

The frontend performs immediate checks for a selected file, PDF extension/type, and the 20 MB limit. The backend remains authoritative and validates:

- Reference Content enabled requires exactly one PDF.
- Reference Content disabled rejects an attached PDF.
- The original filename is nonblank and safe to persist as metadata.
- The declared media type and filename identify a PDF.
- The content begins with a valid PDF signature.
- The content is not empty and is no larger than `20 * 1024 * 1024` bytes.

The upload is processed as transient request data. It may use the web framework's bounded temporary upload handling, but it must not be passed to the existing `SourceDocument` model or committed to PostgreSQL. No PDF text is extracted or persisted.

The API preserves the existing `Idempotency-Key` behavior. A submission lookup that finds an experiment in any run state returns that existing experiment without creating another run or retaining another Gemini upload. Under concurrent submissions with the same key, only the request that wins experiment creation may enqueue generation; losing attempts delete any Gemini file they uploaded.

If local validation fails, the API does not contact Gemini or create an experiment. If a Gemini upload or subsequent database operation fails, the API makes a best-effort deletion of any temporary Gemini file and does not enqueue the generation worker for that failed attempt.

## Persistence

Add a nullable `reference_pdf_filename` string column to `runs`. For a PDF-backed run it stores the original user-visible filename; for all other runs it is null.

The application database must not store:

- PDF bytes.
- Extracted PDF text.
- Base64-encoded PDF data.
- A Gemini file name, URI, or other provider attachment identifier.

Reference Content no longer requires or writes a `reference_content` entry in `condition.factor_inputs` when it is backed by a PDF. Prompt rendering uses the run's attachment state to describe Reference Content as an attached document without embedding document contents.

Run-detail and run-summary responses expose `reference_pdf_filename` so the UI can display the source name and require a fresh upload for manual retry. They must not expose temporary Gemini attachment metadata.

## Gemini Attachment Lifecycle

The API uploads the validated PDF to Gemini's Files API. The Celery generation message contains only the run ID and temporary provider metadata needed to reference and later delete that file: Gemini file name, URI, and MIME type. The Celery payload never contains PDF bytes, and the provider metadata is never stored in PostgreSQL.

The worker builds the Actual Prompt through the existing OpenAI-template or Anthropic-structuring path without the PDF. The PDF is attached only after the Actual Prompt is complete:

- Attach it to the primary assessment-generation call alongside the Actual Prompt and existing generation context.
- Attach it again to a schema-repair call for the same assessment, because repair remains part of final assessment generation.
- Do not attach it to the Anthropic request that structures the Actual Prompt.
- Do not attach it to later LLM evaluation calls.

Automatic Celery/provider retries reuse the same Gemini file metadata. The worker keeps the temporary file while an automatic retry remains pending, then explicitly deletes it after any terminal outcome:

- Successful assessment generation.
- Non-retryable generation failure.
- Exhaustion of automatic provider retries.

If explicit deletion fails, the worker logs the cleanup problem without changing an otherwise successful run to failed. Gemini's automatic file expiration, currently documented as 48 hours, is the cleanup fallback. Application behavior must not depend on the file remaining available for a later manual retry.

If the temporary Gemini file is missing or expired before a generation attempt, the run ends with a sanitized attachment-unavailable error. The UI directs the user to start a manual retry with a fresh PDF.

## Provider Interface

Extend the LLM client generation interface with an optional attachment value containing provider file metadata. With no attachment, it must preserve current request construction exactly. With an attachment, it creates Gemini multipart contents containing the current user message and a PDF file part. System instructions, model settings, response schema, usage tracking, and truncation handling remain unchanged.

Add focused provider operations for:

- Uploading a seekable PDF stream with `application/pdf` and the original display name.
- Referring to the uploaded file during generation.
- Deleting a Gemini file by its provider name.

These operations remain isolated behind the LLM client so API and worker code do not construct Gemini SDK types directly.

## Manual Retry

The retry endpoint supports a multipart PDF upload for a source run whose `reference_pdf_filename` is non-null. It applies the same file validation and Gemini upload sequence as initial experiment creation, creates the next immutable run number, copies the original condition and model settings, records the newly supplied filename on the new run, and enqueues the worker with new temporary Gemini metadata.

A PDF-backed retry without a new attachment returns a conflict response with a stable `reference_pdf_required` code. Supplying a PDF when retrying a run that did not use one is rejected. Existing non-PDF retry requests and behavior remain backward compatible.

## Error Handling and Cleanup

User-correctable validation errors use stable codes and accessible messages for missing PDF, unsupported type, invalid PDF content, empty PDF, and file too large. Provider upload failures return a sanitized submission error and do not expose SDK exceptions, credentials, file URIs, or provider identifiers.

Cleanup is best-effort in every path after a provider upload. Cleanup code is idempotent so repeated deletion attempts and provider `not found` responses are safe. The worker distinguishes an automatic retry from a terminal task result so it does not delete an attachment before the next automatic attempt.

## Testing

Frontend tests verify:

- Reference Content renders a single PDF selector instead of a text area.
- Missing, non-PDF, and over-20-MB files block submission.
- The advisory 100-page copy is visible without page-count enforcement.
- The selected filename appears in factor and Review views.
- Disabling the factor clears the selection.
- Initial creation and PDF-backed retry send multipart requests.
- Manual retry requires a fresh PDF for PDF-backed runs.

Backend tests verify:

- Multipart experiment parsing preserves all existing JSON fields.
- File validation rejects missing, unexpected, invalid, empty, and oversized PDFs.
- Successful creation persists only `reference_pdf_filename` and never creates a `SourceDocument` or binary database value.
- Idempotent and concurrent submissions do not enqueue duplicate work and delete losing temporary uploads.
- The LLM client attaches the PDF on assessment and repair calls only.
- Prompt structuring and evaluation calls remain attachment-free.
- Automatic retries retain attachment metadata until a terminal attempt.
- Success, non-retryable failure, retry exhaustion, and partial setup failure perform cleanup.
- Cleanup failures do not overwrite a successful run result.
- PDF-backed manual retries require and use a fresh upload; non-PDF retries remain compatible.
- The database migration upgrades and downgrades the nullable filename column.

## Documentation References

- Gemini Files API: <https://ai.google.dev/gemini-api/docs/files>
- Gemini PDF processing: <https://ai.google.dev/gemini-api/docs/document-processing>
