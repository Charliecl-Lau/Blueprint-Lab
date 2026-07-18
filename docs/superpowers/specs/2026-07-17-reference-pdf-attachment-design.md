# Reference PDF Attachments Design

## Purpose

Replace the Reference Content prompt factor's free-text input with an upload for one to three PDFs. The PDFs must be attached to the final Gemini assessment-generation request alongside the Actual Prompt, but their bytes and extracted text must never be stored in the application database. The database records only the ordered original PDF filenames on the corresponding run.

## Scope

This change covers the experiment wizard, experiment submission API, run persistence, Gemini temporary-file lifecycle, assessment generation and repair calls, manual run retries, validation, and automated tests.

The following are outside this change:

- Extracting PDF text into `factor_inputs`.
- Saving PDF bytes in PostgreSQL or the existing source-document subsystem.
- Enforcing a PDF page-count limit.
- Supporting more than three PDFs or non-PDF reference attachments.
- Attaching the PDFs to the Anthropic prompt-structuring request.

## User Experience

Reference Content remains one of the selectable Prompt Design Factors. When it is enabled, its text area is replaced by a file selector that accepts one to three PDFs. The interface displays the selected filenames in selection order, the strict `Maximum 3 PDFs; 20 MB per PDF` rule, and the advisory copy `Please do not upload PDFs longer than 100 pages.`

The Review step displays the selected PDF filenames in selection order. Disabling Reference Content clears all selected files and their validation errors. Enabling Reference Content without selecting at least one PDF prevents submission and focuses the file selector through the existing grouped validation dialog. Selecting more than three PDFs also prevents submission.

The application strictly enforces PDF type, a maximum of three files, and a 20 MB byte limit independently for each PDF. There is no additional combined-size limit beyond the three-file maximum. The 100-page message applies to each PDF and is advisory only; neither the browser nor backend counts or rejects pages.

PDF-backed runs cannot use the existing one-click manual retry because their original attachments have been deleted. A manual retry asks the user to select a new set of one to three PDFs. Runs that did not use reference PDFs retain one-click retry behavior.

## Submission and Validation

Experiment creation changes from an application/json request to multipart form data with:

- A JSON part containing the existing experiment fields and prompt-factor configuration.
- A repeated PDF part containing one to three files only when Reference Content is enabled.

The frontend performs immediate checks for a selected file, PDF extension/type, and the 20 MB limit. The backend remains authoritative and validates:

- Reference Content enabled requires at least one and no more than three PDFs.
- Reference Content disabled rejects all attached PDFs.
- Each original filename is nonblank and safe to persist as metadata.
- Each declared media type and filename identify a PDF.
- Each file's content begins with a valid PDF signature.
- Each file is nonempty and no larger than `20 * 1024 * 1024` bytes.
- File order follows the multipart selection order and is preserved through persistence and Gemini request construction.

The uploads are processed as transient request data. They may use the web framework's bounded temporary upload handling, but they must not be passed to the existing `SourceDocument` model or committed to PostgreSQL. No PDF text is extracted or persisted.

The API preserves the existing `Idempotency-Key` behavior. A submission lookup that finds an experiment in any run state returns that existing experiment without creating another run or retaining another set of Gemini uploads. Under concurrent submissions with the same key, only the request that wins experiment creation may enqueue generation; losing attempts delete every Gemini file they uploaded.

If local validation fails, the API does not contact Gemini or create an experiment. If any Gemini upload or subsequent database operation fails, the API makes a best-effort deletion of every temporary Gemini file created by that attempt and does not enqueue the generation worker.

## Persistence

Add a `run_reference_pdfs` child table containing `id`, `run_id`, `ordinal`, and `original_filename`. `run_id` is a foreign key to `runs` with cascading deletion. `ordinal` is zero-based, limited to 0 through 2, and unique per run. A PDF-backed run has one to three ordered filename rows; a run without reference PDFs has none.

The application database must not store:

- PDF bytes.
- Extracted PDF text.
- Base64-encoded PDF data.
- A Gemini file name, URI, or other provider attachment identifier.

Reference Content no longer requires or writes a `reference_content` entry in `condition.factor_inputs` when it is backed by PDFs. Prompt rendering uses the run's attachment state to describe Reference Content as attached documents without embedding document contents.

Run-detail and run-summary responses expose `reference_pdf_filenames` as an ordered string array so the UI can display the source names and require fresh uploads for manual retry. They must not expose temporary Gemini attachment metadata.

## Gemini Attachment Lifecycle

The API uploads each validated PDF to Gemini's Files API in selection order. The Celery generation message contains only the run ID and an ordered list of temporary provider metadata needed to reference and later delete the files: Gemini file name, URI, and MIME type. The Celery payload never contains PDF bytes, and the provider metadata is never stored in PostgreSQL.

The worker builds the Actual Prompt through the existing OpenAI-template or Anthropic-structuring path without the PDFs. The PDFs are attached in their saved order only after the Actual Prompt is complete:

- Attach all files to the primary assessment-generation call alongside the Actual Prompt and existing generation context.
- Attach all files again to a schema-repair call for the same assessment, because repair remains part of final assessment generation.
- Do not attach them to the Anthropic request that structures the Actual Prompt.
- Do not attach them to later LLM evaluation calls.

Automatic Celery/provider retries reuse the same ordered Gemini file metadata. The worker keeps all temporary files while an automatic retry remains pending, then explicitly deletes every file after any terminal outcome:

- Successful assessment generation.
- Non-retryable generation failure.
- Exhaustion of automatic provider retries.

If deletion of one or more files fails, the worker attempts the remaining deletions and logs each cleanup problem without changing an otherwise successful run to failed. Gemini's automatic file expiration, currently documented as 48 hours, is the cleanup fallback. Application behavior must not depend on the files remaining available for a later manual retry.

If any temporary Gemini file is missing or expired before a generation attempt, the run ends with a sanitized attachment-unavailable error. The UI directs the user to start a manual retry with a fresh set of one to three PDFs.

## Provider Interface

Extend the LLM client generation interface with an optional ordered attachment list containing provider file metadata. With no attachments, it must preserve current request construction exactly. With attachments, it creates Gemini multipart contents containing the current user message and one to three PDF file parts in order. System instructions, model settings, response schema, usage tracking, and truncation handling remain unchanged.

Add focused provider operations for:

- Uploading each seekable PDF stream with `application/pdf` and its original display name.
- Referring to ordered uploaded files during generation.
- Deleting each Gemini file by its provider name.

These operations remain isolated behind the LLM client so API and worker code do not construct Gemini SDK types directly.

## Manual Retry

The retry endpoint supports repeated multipart PDF fields for a source run whose `reference_pdf_filenames` array is nonempty. It requires a new set of one to three PDFs, applies the same per-file validation and ordered Gemini upload sequence as initial experiment creation, creates the next immutable run number, copies the original condition and model settings, records the newly supplied filenames on the new run, and enqueues the worker with new ordered temporary Gemini metadata.

A PDF-backed retry without new attachments returns a conflict response with a stable `reference_pdfs_required` code. Supplying more than three files, an invalid file, or any PDFs when retrying a run that did not use them is rejected. Existing non-PDF retry requests and behavior remain backward compatible.

## Error Handling and Cleanup

User-correctable validation errors use stable codes and accessible messages for missing PDFs, too many PDFs, unsupported type, invalid PDF content, empty PDF, and a file over 20 MB. File-specific errors identify the original filename without exposing file contents. Provider upload failures return a sanitized submission error and do not expose SDK exceptions, credentials, file URIs, or provider identifiers.

Cleanup is best-effort in every path after one or more provider uploads. Cleanup code is idempotent, attempts every uploaded file even if an earlier deletion fails, and treats repeated deletion attempts and provider `not found` responses as safe. The worker distinguishes an automatic retry from a terminal task result so it does not delete attachments before the next automatic attempt.

## Testing

Frontend tests verify:

- Reference Content renders a multi-file PDF selector instead of a text area.
- Missing PDFs, more than three PDFs, non-PDF files, and any PDF over 20 MB block submission.
- The advisory 100-page copy is visible without page-count enforcement.
- Selected filenames appear in selection order in factor and Review views.
- Disabling the factor clears all selections.
- Initial creation and PDF-backed retry send multipart requests.
- Manual retry requires a fresh set of one to three PDFs for PDF-backed runs.

Backend tests verify:

- Multipart experiment parsing preserves all existing JSON fields.
- File validation rejects missing, excessive, unexpected, invalid, empty, and individually oversized PDFs.
- Successful creation persists only ordered filename rows and never creates a `SourceDocument` or binary database value.
- Idempotent and concurrent submissions do not enqueue duplicate work and delete all losing temporary uploads.
- The LLM client attaches all PDFs in order on assessment and repair calls only.
- Prompt structuring and evaluation calls remain attachment-free.
- Automatic retries retain all ordered attachment metadata until a terminal attempt.
- Success, non-retryable failure, retry exhaustion, and partial multi-file setup failure clean up every uploaded file.
- Cleanup failures do not overwrite a successful run result.
- PDF-backed manual retries require and use a fresh set of one to three uploads; non-PDF retries remain compatible.
- The database migration upgrades and downgrades the ordered filename child table and its constraints.

## Documentation References

- Gemini Files API: <https://ai.google.dev/gemini-api/docs/files>
- Gemini PDF processing: <https://ai.google.dev/gemini-api/docs/document-processing>
