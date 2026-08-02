# Plan 3: Fully Grounded LLM DOCX Authoring Pipeline

**Goal:** Add the second Gemini call that authors the DOCX-building program, execute it through the self-hosted sandbox, validate its DOCX and rewritten manifest, allow one bounded repair, and atomically make the successful rewrite canonical.

**Depends on:** Plans 1 and 2.

**Unblocks:** Plan 4.

**Architecture:** The worker orchestrates pure, testable components: grounding builder, provider, sandbox client, package verifier, render verifier, manifest verifier, repair classifier, and persistence service. Gemini authors code; the application does not deterministically lay out the production DOCX. Existing `docx_exporter.py` remains available only for legacy runs while the feature flag is off.

**TDD rule:** Every component begins with fixture-driven contract tests. Worker tests mock provider and sandbox boundaries, while verifier tests use checked-in DOCX fixtures. No live model call belongs in the default test suite.

## Proposed files

- Add `backend/schemas/docx_authoring_schema.py`
- Add `backend/services/docx_grounding.py`
- Add `backend/services/docx_authoring_provider.py`
- Add `backend/services/gemini_docx_authoring.py`
- Add `backend/services/docx_sandbox_client.py`
- Add `backend/services/docx_package_verifier.py`
- Add `backend/services/docx_manifest_verifier.py`
- Add `backend/services/docx_render_verifier.py`
- Add `backend/services/docx_repair_policy.py`
- Add `backend/services/docx_authoring_pipeline.py`
- Add `backend/prompts/docx_authoring_system.md`
- Add `backend/prompts/docx_authoring_repair.md`
- Add `docs/docx-design-contract/v1/contract.json`
- Add `docs/docx-design-contract/v1/authoring-guide.md`
- Add controlled reference assets under `docs/docx-design-contract/v1/assets/`
- Add `backend/migrations/versions/20260802_03_docx_rewrite_lifecycle.py`
- Modify `backend/config.py`
- Modify `backend/models/model_call_usage.py`
- Modify `backend/workers/assessment_worker.py`
- Modify `backend/services/document_artifact.py`
- Modify `backend/api/runs.py`
- Add `backend/tests/fixtures/docx_authoring/`
- Add focused tests matching each service filename
- Modify `backend/tests/test_assessment_worker.py`

## Task 1: Check in the versioned design contract and manifest schema

### 1. Write failing schema tests

The manifest must preserve all five mandatory sections and provide typed, step-by-step solutions. Tests reject missing mappings, duplicate IDs, wrong MCQ option counts, missing correct answers, and untyped solution steps.

Representative models:

```python
class ComputationalSolution(BaseModel):
    kind: Literal["computational"]
    knowns_and_target: list[str] = Field(min_length=1)
    governing_equation: str
    substitution: str
    calculation_steps: list[str] = Field(min_length=1)
    final_answer: str
    units: str
    physical_meaning: str
    distractor_analysis: list[DistractorAnalysis]


class ConceptualSolution(BaseModel):
    kind: Literal["conceptual"]
    governing_concept: str
    application_steps: list[str] = Field(min_length=1)
    option_elimination: list[DistractorAnalysis]
    conclusion: str


class RewrittenAssessmentManifest(BaseModel):
    schema_version: Literal["rewritten-assessment/1"]
    metadata: AssessmentMetadata
    questions: list[RewrittenQuestion]
    answer_key: list[AnswerKeyEntry]
    overall_connection: str
    quality_check: list[QualityCheckRow]
    revision_options: list[str] = Field(min_length=3)
```

Every rewritten question includes `source_question_id` and `source_ordinal`. For this approved MCQ experiment, each question has exactly five choices and one correct answer.

### 2. Distill the reference into repository assets

Convert the already approved inspection evidence into a stable contract recording:

- Letter portrait page geometry and margins;
- Aptos/Aptos Display hierarchy and dark-blue palette;
- header rule and `Page X of Y` footer;
- metadata, answer-key, and five-column quality tables;
- alternating pale-blue rows;
- native Word equations where feasible;
- chart-image rules;
- all five required sections and step-by-step solution structure.

Do not copy the user-specific Downloads path into production. If the source DOCX itself is retained, add it only with explicit user approval; otherwise retain the distilled contract, approved hashes, measurements, and controlled derivative assets.

Run:

```powershell
pytest backend/tests/test_docx_authoring_schema.py -q
```

### 3. Commit checkpoint

```text
Define the rewritten assessment and DOCX design contract

This checks in the versioned semantic and visual requirements used by both
Gemini and the validators. Typed solution steps and source-question mappings
make the rewrite usable by the viewer and evaluator, not only by Word.
```

## Task 2: Build deterministic full grounding

### 1. Write failing grounding tests

Given a run fixture, prove the builder includes in this exact stable order:

1. contract and schema versions;
2. run/experiment/condition metadata;
3. immutable original assessment JSON and hashes;
4. exact Actual Prompt, clearly marked as quoted context;
5. original prompt-generation provenance;
6. ordered source-document descriptors and full content;
7. ordered reference-PDF descriptors and provider attachments;
8. the design contract and program envelope;
9. the instruction to retain all five sections and use step-by-step solutions.

Test content delimiters against prompt injection in source documents. Test canonical JSON serialization and a stable SHA-256 grounding hash.

Example:

```python
grounding = build_docx_grounding(run)
assert grounding.original_assessment == run.assessment_versions[0].parsed_json
assert grounding.actual_prompt == run.prompt.actual_prompt
assert [source.ordinal for source in grounding.sources] == [0, 1, 2]
assert grounding.sha256 == sha256(grounding.canonical_bytes).hexdigest()
```

### 2. Implement without truncating source context

This experiment uses full grounding. Do not summarize, retrieve subsets, or auto-fallback to Option B. Fail explicitly before the provider call if a required stored source cannot be reconstructed or its hash differs.

Run:

```powershell
pytest backend/tests/test_docx_grounding.py -q
```

### 3. Commit checkpoint

```text
Assemble complete and hash-bound DOCX grounding

This builds the second call from the immutable original JSON, exact Actual
Prompt, ordered sources, run metadata, and versioned design contract. Stable
serialization makes token experiments and repair attempts auditable.
```

## Task 3: Add the provider-neutral authoring interface and Gemini implementation

### 1. Write failing provider tests

Define the future-compatible boundary now:

```python
class DocxAuthoringProvider(Protocol):
    def author_program(
        self,
        grounding: DocxGrounding,
        *,
        attempt_number: Literal[1, 2],
        repair_context: RepairContext | None = None,
    ) -> AuthoringResult: ...
```

Tests prove the Gemini provider:

- uses `gemini-3.5-flash-lite`;
- requests the strict `DocxProgramEnvelope` schema;
- includes full grounding and attachments;
- does not enable Google's hosted code execution;
- records provider response ID, model version, finish reason, duration, and usage;
- rejects prose, Markdown fences, multiple programs, unknown fields, and hash mismatch;
- uses the same provider instance for the one repair call with structured failure evidence.

Envelope example:

```json
{
  "schema_version": "docx-program-envelope/1",
  "language": "python",
  "entrypoint": "program.py",
  "program": "from docx import Document\n...",
  "expected_outputs": ["assessment.docx", "assessment_manifest.json"],
  "generation_notes": "short non-executable summary"
}
```

### 2. Implement Gemini authoring

Reuse `LLMResult` and token parsing. Extend `ModelCallUsage.stage` with `docx_code_generation` and `docx_code_repair`. Do not merge sandbox time with model duration.

Run:

```powershell
pytest backend/tests/test_gemini_docx_authoring.py backend/tests/test_usage_tracking.py backend/tests/test_model_call_usage.py -q
```

### 3. Commit checkpoint

```text
Generate DOCX programs with Gemini 3.5 Flash-Lite

This adds a provider-neutral authoring boundary and its initial Gemini
implementation. Strict envelopes, full provenance, and separate usage stages
prepare the same pipeline for a later OpenAI Code Interpreter provider.
```

## Task 4: Add the sandbox client

### 1. Write failing client tests

Test authenticated submission, timeouts, bounded retry of transient transport errors only, response-size limits, DOCX/manifest hash verification, replay-safe job IDs, and redacted exceptions. A sandbox execution failure is a pipeline result, not an HTTP retry.

```python
result = client.execute(
    job_id=stable_job_id(run.id, cycle_number, attempt_number),
    program=envelope.program,
    program_sha256=sha256_text(envelope.program),
    grounding_sha256=grounding.sha256,
)
assert result.docx_sha256 == sha256(result.docx_bytes).hexdigest()
```

### 2. Implement the private client

Configuration must include service URL, service-auth secret/workload identity, connect/read timeouts, response-size ceiling, and expected job-image digest. Reject a response produced by another digest.

Run:

```powershell
pytest backend/tests/test_docx_sandbox_client.py -q
```

### 3. Commit checkpoint

```text
Connect the worker to the private DOCX sandbox

This client binds each execution to stable job, program, grounding, and image
hashes. Transport retry is narrow and execution failures remain visible to the
pipeline's repair classifier.
```

## Task 5: Validate the package, manifest, and rendering

### 1. Write malicious and malformed DOCX fixtures first

The package verifier rejects:

- macros, ActiveX, OLE, embedded executables, external relationships, remote templates, and unsupported custom XML;
- zip-slip names, duplicate parts, excessive expanded size or compression ratios;
- unexpected files, symlinks, damaged content types, and missing core parts.

The semantic verifier proves:

- all five section headings exist in order;
- metadata, answer key, quality table, and revision list exist;
- question count and five-choice MCQ structure match the manifest;
- source mappings cover every original question exactly once;
- visible correct answers, step labels, final answers, interpretations, and distractor analysis exist;
- extractable text and OOXML math/relationship evidence agree with the manifest.

The render verifier invokes a pinned headless LibreOffice environment and asserts conversion succeeds, page count is within configured bounds, and every rendered page is non-empty.

### 2. Implement composable reports

```python
@dataclass(frozen=True)
class VerificationReport:
    valid: bool
    issues: tuple[VerificationIssue, ...]
    package_sha256: str
    manifest_sha256: str
    rendered_page_count: int | None
    tool_versions: dict[str, str]
```

Each issue has a stable code, severity, repairability, and sanitized evidence. Verifiers never repair the document themselves.

Run:

```powershell
pytest backend/tests/test_docx_package_verifier.py backend/tests/test_docx_manifest_verifier.py backend/tests/test_docx_render_verifier.py -q
```

### 3. Commit checkpoint

```text
Verify generated DOCX packages and rewritten manifests

This adds package security, semantic completeness, source-mapping, and render
smoke gates. Only a safe document whose visible content agrees with its typed
manifest can become a canonical assessment.
```

## Task 6: Orchestrate one authoring attempt and one bounded repair

### 1. Write the pipeline state-machine tests first

Cover:

- first-attempt success;
- schema failure followed by repair success;
- execution failure followed by repair success;
- semantic/render failure followed by repair success;
- second failure ending in `rewrite_failed`;
- security-policy failure ending immediately without repair;
- transport interruption resuming idempotently from persisted attempt evidence;
- persistence failure leaving version 1 canonical;
- no automatic use of Option B or deterministic exporter.

Classify repairable failures narrowly:

```python
REPAIRABLE = {
    "program_schema_invalid",
    "python_syntax_error",
    "execution_failed",
    "required_output_missing",
    "manifest_invalid",
    "semantic_mismatch",
    "render_failed",
}

NON_REPAIRABLE = {
    "policy_rejected",
    "network_attempt",
    "secret_access_attempt",
    "archive_bomb",
    "embedded_executable",
}
```

### 2. Implement orchestration

```python
def run_docx_authoring(run_id: int) -> PipelineResult:
    grounding = grounding_builder.build(run_id)
    cycle_number = attempt_store.next_cycle_number(run_id)
    for attempt_number in (1, 2):
        authored = provider.author_program(
            grounding,
            attempt_number=attempt_number,
            repair_context=repair_context,
        )
        executed = sandbox.execute(authored.envelope, grounding)
        verified = verifier.verify(executed, grounding)
        attempt_store.record(cycle_number, authored, executed, verified)
        if verified.valid:
            return canonicalizer.persist(run_id, executed, verified)
        if attempt_number == 2 or not repair_policy.may_repair(verified):
            return PipelineResult.rewrite_failed(verified)
        repair_context = RepairContext.from_report(verified)
    raise AssertionError("bounded loop exhausted")
```

Repair grounding includes the original full grounding plus the previous exact program, bounded logs, and structured verifier issues. It is another measured LLM call. Never send secrets or raw application logs. A rewrite-only retry after terminal failure invokes the same function as a new cycle; it appends two new attempt slots without changing prior attempts.

### 3. Commit checkpoint

```text
Orchestrate bounded LLM-authored DOCX generation

This composes authoring, isolated execution, validation, one repair, and atomic
canonicalization. Security failures stop immediately, while ordinary authoring
defects receive exactly one evidence-grounded repair attempt.
```

## Task 7: Integrate the pipeline into the worker behind a manual feature flag

### 1. Write failing worker tests

For `DOCX_GENERATION_BACKEND=self_hosted_code`, assert this state sequence:

```text
pending -> prompting -> generating -> docx_authoring -> docx_executing
-> docx_validating -> complete
```

Allow `docx_repairing` before the second attempt. On terminal rewrite failure, set `rewrite_failed`, retain viewer access to version 1, disable DOCX download and grading of the rewrite, and preserve error evidence. For the legacy flag, prove current `documenting -> complete` behavior remains unchanged.

### 2. Update status constraints and worker code

Add statuses and the two DOCX usage-stage values through the lifecycle migration; update API/frontend enums in Plan 4. In the worker, persist version 1 before starting authoring. Replace the deterministic artifact call only inside the feature-flag branch:

```python
if settings.docx_generation_backend == "self_hosted_code":
    result = docx_authoring_pipeline.run(run.id)
    if not result.succeeded:
        mark_rewrite_failed(db, run, result)
        return
else:
    save_assessment_artifact(db, run)  # legacy only
```

Automated evaluation starts only after version 2 becomes canonical. Never evaluate version 1 and later relabel those results as version 2.

Run:

```powershell
pytest backend/tests/test_assessment_worker.py backend/tests/test_run_progress.py backend/tests/test_api_runs.py -q
```

### 3. Commit checkpoint

```text
Route experimental DOCX runs through LLM authoring

This gates the new second-call workflow behind an explicit backend setting and
adds persisted authoring, execution, validation, repair, and failure states.
Legacy deterministic export remains available only when the experiment is off.
```

## Plan 3 completion gate

```powershell
pytest backend/tests/test_docx_authoring_schema.py backend/tests/test_docx_grounding.py backend/tests/test_gemini_docx_authoring.py -q
pytest backend/tests/test_docx_sandbox_client.py backend/tests/test_docx_package_verifier.py backend/tests/test_docx_manifest_verifier.py backend/tests/test_docx_render_verifier.py -q
pytest backend/tests/test_docx_authoring_pipeline.py backend/tests/test_assessment_worker.py backend/tests/test_usage_tracking.py -q
pytest backend/tests -q
```

Run one opt-in live experiment against Gemini and the sandbox, then inspect every rendered page against the design contract. Record exact stage tokens but do not add an automatic token threshold. Plan 3 is complete only when the original remains immutable, a validated rewrite becomes canonical atomically, and no deterministic backend code authored the production document layout.
