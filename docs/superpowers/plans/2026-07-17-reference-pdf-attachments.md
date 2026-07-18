# Reference PDF Attachments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Reference Content text entry with one to three temporary PDF attachments, enforce 20 MB per file, persist only ordered filenames, attach the PDFs to Gemini assessment and repair requests, and require fresh PDFs for manual retry.

**Architecture:** The browser submits experiment JSON and ordered PDFs as multipart form data. The API validates each file, uploads it to Gemini Files, persists only ordered filename rows, and sends temporary provider metadata through Celery; the worker attaches those files only to assessment and repair calls and deletes every temporary file on terminal completion. PDF-backed retries repeat the upload process, while non-PDF runs preserve their existing retry route.

**Tech Stack:** React 19, TypeScript 6, Vitest/Testing Library, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, Celery/Redis, Google Gen AI SDK 1.47, pytest.

## Global Constraints

- Accept one to three PDFs when Reference Content is enabled.
- Enforce `20 * 1024 * 1024` bytes independently per PDF; do not enforce a combined-size limit.
- Display but do not enforce: `Please do not upload PDFs longer than 100 pages.`
- Never persist PDF bytes, extracted text, base64 data, Gemini file names, or Gemini URIs in PostgreSQL.
- Persist ordered original filenames only, associated with the run.
- Attach PDFs only to final assessment generation and schema repair, never to prompt structuring or LLM evaluation.
- Retain temporary Gemini files across automatic task retries and delete all files after a terminal outcome.
- Require a fresh set of one to three PDFs for manual retry of a PDF-backed run.
- Every commit must have a subject and explanatory paragraph body, with no attribution trailers.
- Preserve unrelated working-tree changes.

---

## File Structure

- `backend/models/run.py`: add the ordered run-to-filename model and relationships.
- `backend/models/__init__.py`: export the new model.
- `backend/migrations/versions/20260717_03_reference_pdf_attachments.py`: create the filename-only child table.
- `backend/schemas/experiment_schema.py`: allow PDF-backed Reference Content without text and report filenames in run summaries.
- `backend/schemas/run_schema.py`: report ordered filenames in run API schemas.
- `backend/services/reference_pdfs.py`: own upload validation, limits, safe filename metadata, and attachment conversion.
- `backend/services/llm_client.py`: own Gemini upload/reference/delete operations and optional ordered attachments.
- `backend/services/experiment_service.py`: validate the factor/filename contract and persist filename rows atomically.
- `backend/services/run_service.py`: create PDF-backed immutable retries with new filename rows.
- `backend/services/actual_prompt.py`: render a deterministic attached-PDF instruction instead of PDF text.
- `backend/api/experiments.py`: parse multipart creation, upload validated PDFs, enforce idempotency, enqueue metadata, and clean up partial uploads.
- `backend/api/runs.py`: expose filenames and support multipart PDF-backed retries.
- `backend/workers/assessment_worker.py`: attach ordered PDFs only to assessment/repair and clean them up at terminal completion.
- `frontend/src/types/index.ts`: represent ordered filename metadata.
- `frontend/src/api/client.ts`: support FormData without forcing JSON headers.
- `frontend/src/api/experiments.ts`: serialize experiment creation as multipart.
- `frontend/src/api/runs.ts`: serialize PDF-backed retry as multipart.
- `frontend/src/validation/experimentValidation.ts`: validate Reference Content files separately from text factors.
- `frontend/src/components/PromptFactorFields.tsx`: render the multi-PDF selector and selection list.
- `frontend/src/pages/InputPanelPage.tsx`: own PDF state, review display, multipart submission, and clearing behavior.
- `frontend/src/pages/AssessmentViewerPage.tsx`: require fresh PDFs in the retry dialog when the selected run is PDF-backed.
- `frontend/src/index.css`: style file guidance, filename list, and retry upload controls.
- Existing and new backend/frontend test files listed in each task provide the test-first contract.

---

### Task 1: Persist Ordered PDF Filenames Only

**Files:**
- Create: `backend/migrations/versions/20260717_03_reference_pdf_attachments.py`
- Modify: `backend/models/run.py`
- Modify: `backend/models/__init__.py`
- Modify: `backend/schemas/experiment_schema.py`
- Modify: `backend/schemas/run_schema.py`
- Modify: `backend/tests/test_run_models.py`
- Modify: `backend/tests/integration/test_run_tracking_migration.py`

**Interfaces:**
- Produces: `RunReferencePdf(run_id: int, ordinal: int, original_filename: str)`.
- Produces: `Run.reference_pdfs: list[RunReferencePdf]` ordered by `ordinal`.
- Produces: `Run.reference_pdf_filenames -> list[str]`.
- Produces: `GenerationSummary.reference_pdf_filenames` and `RunSummary.reference_pdf_filenames`.

- [ ] **Step 1: Write failing model and schema tests**

Add a test that constructs a run with two metadata-only rows and proves order and API serialization:

```python
from backend.models.run import RunReferencePdf

def test_run_records_only_ordered_reference_pdf_filenames(test_db):
    experiment = Experiment(
        course="C", topic="T", learning_objectives="L",
        assessment_type="mixed", difficulty="D", number_of_questions=1,
    )
    condition = Condition(
        experiment=experiment, prompt_structure="openai",
        factor_inputs={}, condition_label="Reference PDFs",
    )
    run = Run(experiment=experiment, condition=condition, run_number=1)
    run.reference_pdfs = [
        RunReferencePdf(ordinal=1, original_filename="second.pdf"),
        RunReferencePdf(ordinal=0, original_filename="first.pdf"),
    ]
    test_db.add(experiment)
    test_db.commit()
    test_db.refresh(run)

    assert run.reference_pdf_filenames == ["first.pdf", "second.pdf"]
    assert not hasattr(run.reference_pdfs[0], "content")
    assert not hasattr(run.reference_pdfs[0], "provider_uri")
```

Extend the migration integration test to assert the table has exactly metadata columns plus its primary key, foreign key, and constraints:

```python
columns = {item["name"] for item in inspector.get_columns("run_reference_pdfs")}
assert columns == {"id", "run_id", "ordinal", "original_filename"}
assert {item["name"] for item in inspector.get_unique_constraints("run_reference_pdfs")} == {
    "uq_run_reference_pdfs_run_ordinal"
}
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m pytest backend/tests/test_run_models.py backend/tests/integration/test_run_tracking_migration.py -q
```

Expected: FAIL because `RunReferencePdf`, the relationship, and migration table do not exist.

- [ ] **Step 3: Add the model, migration, and response fields**

Add the model and property in `backend/models/run.py`:

```python
class RunReferencePdf(Base):
    __tablename__ = "run_reference_pdfs"
    __table_args__ = (
        CheckConstraint("ordinal >= 0 AND ordinal <= 2", name="ck_run_reference_pdfs_ordinal"),
        UniqueConstraint("run_id", "ordinal", name="uq_run_reference_pdfs_run_ordinal"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    run: Mapped["Run"] = relationship(back_populates="reference_pdfs")
```

Add to `Run`:

```python
reference_pdfs: Mapped[list["RunReferencePdf"]] = relationship(
    back_populates="run",
    cascade="all, delete-orphan",
    order_by="RunReferencePdf.ordinal",
)

@property
def reference_pdf_filenames(self) -> list[str]:
    return [item.original_filename for item in self.reference_pdfs]
```

Create revision `20260717_03` over `20260717_02` with `run_id`, `ordinal`, and `original_filename`, the named check/unique constraints, and `ondelete="CASCADE"`. Downgrade drops only `run_reference_pdfs`. Export `RunReferencePdf`, then add `reference_pdf_filenames: list[str] = Field(default_factory=list)` to `GenerationSummary`, `RunSummary`, `RunDetail`, and `RecentRun` where applicable.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/models/run.py backend/models/__init__.py backend/schemas/experiment_schema.py backend/schemas/run_schema.py backend/migrations/versions/20260717_03_reference_pdf_attachments.py backend/tests/test_run_models.py backend/tests/integration/test_run_tracking_migration.py
git commit -m "Store ordered reference PDF filenames" -m "Add metadata-only filename rows linked to each run so one to three reference PDFs can be identified without persisting file contents or provider attachment identifiers."
```

---

### Task 2: Validate PDFs and Encapsulate Gemini File Operations

**Files:**
- Create: `backend/services/reference_pdfs.py`
- Create: `backend/tests/test_reference_pdfs.py`
- Modify: `backend/services/llm_client.py`
- Modify: `backend/tests/test_llm_client.py`

**Interfaces:**
- Produces: `MAX_REFERENCE_PDF_BYTES = 20 * 1024 * 1024` and `MAX_REFERENCE_PDFS = 3`.
- Produces: `ValidatedReferencePdf(filename: str, content: bytes)`.
- Produces: `ProviderFileAttachment(name: str, uri: str, mime_type: str)` with `to_dict()`/`from_dict()`.
- Produces: `async read_reference_pdfs(files: list[UploadFile]) -> list[ValidatedReferencePdf]`.
- Produces: `LLMClient.upload_pdf(pdf)`, `LLMClient.delete_file(name)`, and `LLMClient.generate(..., attachments=())`.

- [ ] **Step 1: Write failing validation tests**

Cover one-to-three success, fourth-file rejection, per-file size enforcement, MIME/extension/signature failures, empty input, and order:

```python
def upload(name: str, content: bytes = b"%PDF-1.7\nvalid", media_type: str = "application/pdf"):
    return UploadFile(
        filename=name,
        file=BytesIO(content),
        headers=Headers({"content-type": media_type}),
    )

@pytest.mark.asyncio
async def test_reads_three_pdfs_in_order():
    files = [upload("one.pdf"), upload("two.pdf"), upload("three.pdf")]
    result = await read_reference_pdfs(files)
    assert [item.filename for item in result] == ["one.pdf", "two.pdf", "three.pdf"]

@pytest.mark.asyncio
async def test_rejects_each_pdf_over_20_mb():
    with pytest.raises(ReferencePdfValidationError) as raised:
        await read_reference_pdfs([upload("large.pdf", b"%PDF-1.7\n" + b"x" * MAX_REFERENCE_PDF_BYTES)])
    assert raised.value.code == "reference_pdf_too_large"
```

Import `BytesIO`, `Headers`, and `UploadFile` for the helper; a valid test payload begins with `b"%PDF-"`.

- [ ] **Step 2: Write failing LLM attachment tests**

Assert upload configuration, ordered multipart contents, unchanged text-only contents, and delete behavior:

```python
def test_llm_client_attaches_ordered_provider_files():
    attachments = [
        ProviderFileAttachment("files/one", "https://files/one", "application/pdf"),
        ProviderFileAttachment("files/two", "https://files/two", "application/pdf"),
    ]
    with patch("backend.services.llm_client.genai.Client") as client:
        client.return_value.models.generate_content.return_value = gemini_response()
        LLMClient().generate("system", "user", attachments=attachments)
    contents = client.return_value.models.generate_content.call_args.kwargs["contents"]
    assert contents[0].text == "user"
    assert [part.file_data.file_uri for part in contents[1:]] == [
        "https://files/one", "https://files/two"
    ]
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
python -m pytest backend/tests/test_reference_pdfs.py backend/tests/test_llm_client.py -q
```

Expected: FAIL because the validation module, attachment dataclass, and LLM methods are absent.

- [ ] **Step 4: Implement bounded validation and provider isolation**

In `reference_pdfs.py`, read each upload in 1 MB chunks and stop as soon as its accumulated length exceeds the per-file maximum. Validate count before reads; require `.pdf`, `application/pdf`, nonempty content, and leading `%PDF-`. Normalize the saved name with `Path(filename).name` and reject blank results.

In `llm_client.py`, use the installed SDK signatures:

```python
uploaded = self._client.files.upload(
    file=BytesIO(pdf.content),
    config=types.UploadFileConfig(
        display_name=pdf.filename,
        mime_type="application/pdf",
    ),
)
return ProviderFileAttachment(
    name=uploaded.name,
    uri=uploaded.uri,
    mime_type=uploaded.mime_type or "application/pdf",
)
```

Build generation contents as `[types.Part.from_text(text=user_message), *file_parts]`, where each file part is `types.Part.from_uri(file_uri=item.uri, mime_type=item.mime_type)`. Keep `contents=user_message` exactly for an empty attachment list. Deletion calls `self._client.files.delete(name=name)`.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 3 command. Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/services/reference_pdfs.py backend/services/llm_client.py backend/tests/test_reference_pdfs.py backend/tests/test_llm_client.py
git commit -m "Add temporary Gemini PDF transport" -m "Validate up to three PDFs at 20 MB per file and isolate Gemini upload, ordered attachment, and deletion operations behind the LLM client without introducing database persistence."
```

---

### Task 3: Create Experiments Through Multipart Uploads

**Files:**
- Modify: `backend/schemas/experiment_schema.py`
- Modify: `backend/services/experiment_service.py`
- Modify: `backend/api/experiments.py`
- Modify: `backend/tests/test_experiment_schemas.py`
- Modify: `backend/tests/test_experiment_service.py`
- Modify: `backend/tests/test_api_experiments.py`

**Interfaces:**
- Consumes: `ValidatedReferencePdf`, `ProviderFileAttachment`, and `RunReferencePdf`.
- Produces: `create_experiment_with_run(..., reference_pdf_filenames: Sequence[str])`.
- Produces: multipart `POST /experiments` with `payload` JSON and repeated `reference_pdfs` fields.
- Produces: queued call `run_generation_pipeline.delay(run.id, [attachment_dict, ...])`.

- [ ] **Step 1: Write failing schema/service tests**

Change the enabled-factor validator so text remains required for Concept Bridge, Few-shot, and Reasoning Guidance but not PDF-backed Reference Content. Add service tests:

```python
def test_reference_content_requires_filename_metadata(valid_payload, test_db):
    valid_payload["factors"]["reference_content"] = True
    payload = ExperimentCreate(**valid_payload)
    with pytest.raises(ExperimentValidationError) as raised:
        create_experiment_with_run(test_db, payload, "pdf-required", [])
    assert raised.value.issues[0].field == "reference_pdfs"

def test_service_persists_ordered_filenames_without_factor_text(valid_payload, test_db):
    valid_payload["factors"]["reference_content"] = True
    payload = ExperimentCreate(**valid_payload)
    _, run, created = create_experiment_with_run(
        test_db, payload, "pdfs", ["one.pdf", "two.pdf"]
    )
    assert created is True
    assert run.reference_pdf_filenames == ["one.pdf", "two.pdf"]
    assert "reference_content" not in run.condition.factor_inputs
```

- [ ] **Step 2: Write failing multipart API tests**

Post `data={"payload": json.dumps(valid_payload())}` with repeated files and patch `LLMClient`. Assert:

```python
assert response.status_code == 200
assert response.json()["runs"][0]["reference_pdf_filenames"] == ["one.pdf", "two.pdf"]
delay.assert_called_once_with(run_id, [first.to_dict(), second.to_dict()])
assert test_db.query(SourceDocument).count() == 0
```

Add cases for missing files, disabled factor plus files, too many files, invalid PDF, upload failure cleanup, duplicate idempotency without a second upload/enqueue, and partial second-upload failure deleting the first provider file.

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
python -m pytest backend/tests/test_experiment_schemas.py backend/tests/test_experiment_service.py backend/tests/test_api_experiments.py -q
```

Expected: FAIL because Reference Content still requires text and `/experiments` still expects JSON.

- [ ] **Step 4: Implement service persistence and multipart orchestration**

Update the schema validator:

```python
for name, enabled in self.factors.model_dump().items():
    if name == "reference_content":
        continue
    value = getattr(self.factor_inputs, name)
    if enabled and (value is None or not value.strip()):
        raise ValueError(f"Enabled factor '{name}' requires content")
```

Have `create_experiment_with_run` validate enabled/filename agreement, enforce 1-3 names defensively, create `RunReferencePdf` rows in ordinal order before commit, and keep idempotency race handling inside the service.

Change the endpoint to accept `payload: str = Form(...)` and `reference_pdfs: list[UploadFile] | None = File(default=None)`. Parse with `ExperimentCreate.model_validate_json(payload)`, call `read_reference_pdfs`, return an existing idempotent graph before provider upload when possible, upload files in order, then persist/enqueue. Use a helper that attempts deletion of every accumulated provider file in reverse upload order when setup fails or loses an idempotency race.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 3 command. Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/schemas/experiment_schema.py backend/services/experiment_service.py backend/api/experiments.py backend/tests/test_experiment_schemas.py backend/tests/test_experiment_service.py backend/tests/test_api_experiments.py
git commit -m "Accept reference PDFs during experiment creation" -m "Move experiment creation to multipart input, persist ordered filenames only, upload PDFs temporarily to Gemini, preserve idempotency, and clean partial provider state before any worker starts."
```

---

### Task 4: Render Attachment-Aware Prompts and Manage Worker Cleanup

**Files:**
- Modify: `backend/services/actual_prompt.py`
- Modify: `backend/workers/assessment_worker.py`
- Modify: `backend/tests/test_actual_prompt.py`
- Modify: `backend/tests/test_worker.py`

**Interfaces:**
- Consumes: ordered `ProviderFileAttachment` dictionaries passed to the task.
- Produces: `render_openai_actual_prompt(..., reference_pdf_filenames=())` and `build_structure_input(..., reference_pdf_filenames=())`.
- Produces: `run_generation_pipeline(run_id, attachment_metadata=None)`.

- [ ] **Step 1: Write failing prompt tests**

Assert PDF-backed rendering includes metadata-only instructions and no extracted content:

```python
assert "Reference Content:\nUse the attached PDF files in order: one.pdf, two.pdf." in rendered
assert "PDF text" not in rendered
```

For Anthropic structure input, assert it says the PDFs will be supplied during final generation but contains no attachment object or bytes.

- [ ] **Step 2: Write failing worker attachment and cleanup tests**

Add tests proving:

```python
assert llm.generate.call_args_list[0].kwargs.get("attachments") is None  # Anthropic structure
assert llm.generate.call_args_list[1].kwargs["attachments"] == attachments  # assessment
assert llm.generate.call_args_list[2].kwargs["attachments"] == attachments  # repair
assert llm.delete_file.call_args_list == [call("files/one"), call("files/two")]
```

Also cover text-only runs, successful generation, non-retryable failure, missing run, one cleanup deletion failing while the next proceeds, `celery.exceptions.Retry` preserving all files, and exhausted retry cleanup.

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
python -m pytest backend/tests/test_actual_prompt.py backend/tests/test_worker.py -q
```

Expected: FAIL because prompt functions do not accept filenames and the worker does not accept or delete attachments.

- [ ] **Step 4: Implement attachment-aware prompt text**

Use one deterministic helper for both prompt structures:

```python
def _reference_pdf_instruction(filenames: Sequence[str]) -> str:
    joined = ", ".join(filenames)
    return f"Use the attached PDF files in order as reference content: {joined}."
```

When Reference Content is enabled, render this instruction instead of indexing `factor_inputs["reference_content"]`. Do not include it when the factor is disabled.

- [ ] **Step 5: Implement task attachment lifecycle**

Deserialize attachment dictionaries at task entry. Pass no attachment argument to the actual-prompt provider call. Pass the ordered list to assessment and repair calls. Wrap the pipeline so `celery.exceptions.Retry` re-raises without cleanup, while every other return or exception triggers per-file best-effort deletion. Treat provider not-found deletion as success and sanitize an unavailable-file generation error as `reference_pdf_unavailable`.

- [ ] **Step 6: Run tests and verify GREEN**

Run the Step 3 command. Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/services/actual_prompt.py backend/workers/assessment_worker.py backend/tests/test_actual_prompt.py backend/tests/test_worker.py
git commit -m "Attach PDFs during assessment generation" -m "Render metadata-only reference instructions, attach ordered Gemini files to assessment and repair calls, preserve them across automatic retries, and delete every temporary file after terminal outcomes."
```

---

### Task 5: Require Fresh PDFs for PDF-Backed Manual Retries

**Files:**
- Modify: `backend/services/run_service.py`
- Modify: `backend/api/runs.py`
- Modify: `backend/tests/test_run_service.py`
- Modify: `backend/tests/test_api_runs.py`

**Interfaces:**
- Produces: `retry_run(..., reference_pdf_filenames: Sequence[str] | None)`.
- Produces: multipart PDF-backed `POST /runs/{run_id}/retry` and unchanged empty-body retry for non-PDF runs.
- Produces: stable `409` detail code `reference_pdfs_required`.

- [ ] **Step 1: Write failing service tests**

Verify a PDF-backed source rejects absent filenames, accepts one-to-three new names, copies model settings/source snapshots, does not copy old filename rows, and leaves the original immutable. Verify a non-PDF source rejects supplied names.

```python
with pytest.raises(HTTPException) as raised:
    retry_run(test_db, original.id)
assert raised.value.status_code == 409
assert raised.value.detail["code"] == "reference_pdfs_required"
```

- [ ] **Step 2: Write failing API tests**

Patch Gemini upload/delete and task enqueue. Assert a PDF-backed retry without files returns 409, a multipart retry stores new ordered filenames and enqueues new attachment metadata, partial upload failures clean up, and a non-PDF retry still calls `POST /runs/{id}/retry` with no form body.

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
python -m pytest backend/tests/test_run_service.py backend/tests/test_api_runs.py -q
```

Expected: FAIL because retries do not inspect or replace PDF metadata.

- [ ] **Step 4: Implement retry contracts**

Make the service branch on `bool(original.reference_pdfs)`. PDF-backed runs require 1-3 fresh filenames; non-PDF runs require none. Reuse `_create_run` with a filename argument that creates new ordered rows while continuing to snapshot existing persistent source-document bindings.

Change the endpoint to accept optional repeated `reference_pdfs: list[UploadFile]` while remaining callable with an empty body. For PDF-backed originals, validate/upload/enqueue exactly as experiment creation does. Extract shared upload-and-cleanup helpers into `reference_pdfs.py` if Task 3 left duplicate orchestration.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Step 3 command. Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/services/run_service.py backend/api/runs.py backend/tests/test_run_service.py backend/tests/test_api_runs.py backend/services/reference_pdfs.py
git commit -m "Require fresh PDFs for run retries" -m "Keep non-PDF retries unchanged while making PDF-backed retries validate and upload a new ordered attachment set for the new immutable run."
```

---

### Task 6: Replace Reference Content Text with Multi-PDF Input

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/experiments.ts`
- Modify: `frontend/src/validation/experimentValidation.ts`
- Modify: `frontend/src/validation/experimentValidation.test.ts`
- Modify: `frontend/src/components/PromptFactorFields.tsx`
- Modify: `frontend/src/pages/InputPanelPage.tsx`
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Produces: `Run.reference_pdf_filenames?: string[]`.
- Produces: `ExperimentFormValues.referencePdfs: File[]`.
- Produces: `experimentsApi.create(payload, referencePdfs, idempotencyKey)` using `FormData`.

- [ ] **Step 1: Write failing validation tests**

Add `MAX_REFERENCE_PDF_BYTES` and validate missing, count, extension/type, and per-file size:

```typescript
const pdf = (size: number, name = 'reference.pdf') =>
  new File([new Uint8Array(size)], name, { type: 'application/pdf' })

expect(validateExperimentForm({
  ...validForm,
  enabled: { ...validForm.enabled, referenceContent: true },
  referencePdfs: [],
})).toContainEqual(expect.objectContaining({ field: 'factor-referenceContent-pdfs' }))

expect(validateExperimentForm({
  ...validForm,
  enabled: { ...validForm.enabled, referenceContent: true },
  referencePdfs: [pdf(20 * 1024 * 1024 + 1)],
}))
  .toContainEqual(expect.objectContaining({ message: expect.stringContaining('20 MB') }))
```

- [ ] **Step 2: Write failing component/submission tests**

Assert Reference Content shows `input[type=file][multiple][accept="application/pdf,.pdf"]`, the maximum/advisory copy, ordered filename list, clearing on disable, Review filenames, and multipart fields. Inspect FormData directly:

```typescript
expect(init?.body).toBeInstanceOf(FormData)
const form = init?.body as FormData
expect(JSON.parse(String(form.get('payload'))).factor_inputs.reference_content).toBeUndefined()
expect(form.getAll('reference_pdfs').map((item) => (item as File).name))
  .toEqual(['one.pdf', 'two.pdf'])
expect(new Headers(init?.headers).has('Content-Type')).toBe(false)
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
npm test -- --run src/validation/experimentValidation.test.ts src/App.test.tsx
```

Working directory: `frontend`. Expected: FAIL because Reference Content is still a textarea and requests are JSON.

- [ ] **Step 4: Implement file state, validation, and rendering**

Keep `content` for the three text factors and add `referencePdfs` separately. Give `PromptFactorFields` `referencePdfs` and `onReferencePdfs`. Render the file input only for `referenceContent`; all other enabled factors retain textareas. Convert `event.currentTarget.files` to `Array.from(...)`, preserve order, and clear the native input through a keyed rerender when the factor is disabled.

Render:

```tsx
<input
  id="factor-referenceContent-pdfs"
  type="file"
  accept="application/pdf,.pdf"
  multiple
  onChange={(event) => onReferencePdfs(Array.from(event.currentTarget.files ?? []))}
/>
<small>Maximum 3 PDFs; 20 MB per PDF.</small>
<small>Please do not upload PDFs longer than 100 pages.</small>
```

- [ ] **Step 5: Implement FormData transport**

Make the API request helper set JSON content type only for JSON bodies. In `experimentsApi.create`, append `payload` as JSON and append each file under `reference_pdfs` in order. Omit `factor_inputs.reference_content` entirely. Update section-complete and Review logic to use `referencePdfs.length > 0`.

- [ ] **Step 6: Run tests, build, and verify GREEN**

Run from `frontend`:

```powershell
npm test -- --run src/validation/experimentValidation.test.ts src/App.test.tsx
npm run build
```

Expected: tests PASS and TypeScript/Vite build succeeds.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/api/experiments.ts frontend/src/validation/experimentValidation.ts frontend/src/validation/experimentValidation.test.ts frontend/src/components/PromptFactorFields.tsx frontend/src/pages/InputPanelPage.tsx frontend/src/index.css frontend/src/App.test.tsx
git commit -m "Add multi-PDF reference input" -m "Replace Reference Content text entry with an accessible one-to-three PDF selector, enforce the 20 MB per-file rule, show filenames in review, and submit ordered files as multipart form data."
```

---

### Task 7: Add PDF-Aware Retry UI and Complete Verification

**Files:**
- Modify: `frontend/src/api/runs.ts`
- Modify: `frontend/src/pages/AssessmentViewerPage.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/index.css`
- Modify: `frontend/e2e/run-lifecycle.spec.ts`
- Modify: `README.md`
- Modify: `docs/RUN_LIFECYCLE_AND_TOKEN_ACCOUNTING.md`

**Interfaces:**
- Consumes: `Run.reference_pdf_filenames`.
- Produces: `runsApi.retry(id, referencePdfs?)`.
- Produces: retry dialog that conditionally requires one-to-three fresh PDFs.

- [ ] **Step 1: Write failing retry UI tests**

For a run response containing `reference_pdf_filenames: ['old.pdf']`, assert the retry dialog shows a fresh multi-file selector, old filename context, both limit messages, and disables confirmation until valid files are chosen. Assert the resulting FormData has ordered `reference_pdfs`. Retain the existing test proving non-PDF retry sends one POST after confirmation without showing a file input.

- [ ] **Step 2: Run the retry test and verify RED**

Run from `frontend`:

```powershell
npm test -- --run src/App.test.tsx -t "retry"
```

Expected: FAIL because the retry dialog cannot select or submit PDFs.

- [ ] **Step 3: Implement conditional retry upload**

Add retry file/error state. When `selected.reference_pdf_filenames?.length` is nonzero, render the same accept/multiple/count/per-file validation contract as the creation form and call `runsApi.retry(selectedId, retryPdfs)`. Otherwise call `runsApi.retry(selectedId)` exactly as today. Clear retry files when closing the dialog or after successful navigation.

Implement `runsApi.retry` so a provided list creates FormData with repeated `reference_pdfs`; an absent list retains `api.post(..., {})` for backward compatibility.

- [ ] **Step 4: Update end-to-end coverage and documentation**

In Playwright, create two small in-memory PDF payloads with `page.setInputFiles`, intercept multipart experiment creation, verify filenames on Review, and return a run response containing the same ordered filename list. Add README/API documentation for multipart fields, one-to-three count, 20 MB per-file enforcement, advisory page guidance, filename-only persistence, temporary Gemini retention, and fresh-upload retry behavior. Remove the lifecycle document's statement that attachment behavior is out of scope.

- [ ] **Step 5: Run complete verification**

Run:

```powershell
python -m pytest backend/tests -q
```

Run from `frontend`:

```powershell
npm test -- --run
npm run lint
npm run build
npx playwright test e2e/run-lifecycle.spec.ts
```

Expected: all backend and frontend tests pass, lint is clean, build succeeds, and the run-lifecycle browser test passes.

- [ ] **Step 6: Verify persistence and secret boundaries**

Run:

```powershell
rg -n "provider_uri|gemini_file|LargeBinary|extracted_text" backend/models backend/migrations/versions/20260717_03_reference_pdf_attachments.py
```

Expected: the new table contains no provider/file-content fields; any `LargeBinary` or `extracted_text` matches belong only to pre-existing unrelated models.

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; status lists only intentional feature files plus the user's pre-existing unrelated changes.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/api/runs.ts frontend/src/pages/AssessmentViewerPage.tsx frontend/src/App.test.tsx frontend/src/index.css frontend/e2e/run-lifecycle.spec.ts README.md docs/RUN_LIFECYCLE_AND_TOKEN_ACCOUNTING.md
git commit -m "Require PDFs when retrying attached runs" -m "Add a fresh-upload retry experience for PDF-backed runs, retain one-click retries elsewhere, and document and verify the complete temporary attachment lifecycle."
```
