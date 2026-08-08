# GPT-5.6 Luna Direct DOCX Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test a pipeline that preserves actual-prompt-driven assessment JSON generation, then uses a second GPT-5.6 Luna call with Code Interpreter to create the final DOCX without LibreOffice.

**Architecture:** The existing actual-prompt creation, assessment JSON generation, schema validation, repair, and persistence stages remain intact. A new `luna_direct` document backend sends only trusted, validated assessment JSON plus a bounded DOCX authoring contract to GPT-5.6 Luna with an ephemeral Code Interpreter container, immediately downloads the generated `.docx`, verifies its package and canonical content without rendering it in LibreOffice, and stores it through the existing artifact model. Existing `legacy`, `self_hosted_code`, and `agentic_tools` document backends remain available.

**Tech Stack:** Python 3, FastAPI, Celery, SQLAlchemy, Pydantic 2, OpenAI Python SDK Responses API, OpenAI Code Interpreter containers, `python-docx`, ZIP/XML validation, pytest, React/TypeScript.

## Global Constraints

- Use the exact model `gpt-5.6-luna` for every LLM call in this branch.
- Preserve the current question-generation sequence: create actual prompt, generate assessment JSON from it, validate/repair JSON, and persist JSON as canonical content.
- Do not introduce a direct question-generation route that bypasses the actual prompt.
- Add `luna_direct` as the default DOCX backend on this branch.
- `luna_direct` must generate a real `.docx` in an OpenAI Code Interpreter container and download it before the container expires.
- `luna_direct` must not invoke LibreOffice.
- Validate the downloaded DOCX structurally and against canonical assessment JSON; visual rendering is intentionally outside this experimental path.
- Preserve `legacy`, `self_hosted_code`, and `agentic_tools` as selectable alternatives.
- Preserve retry safety, token accounting, model provenance, artifact hashing, and the original assessment when DOCX creation fails.
- Do not add `Co-Authored-By` or attribution trailers. Every commit requires a subject and explanatory paragraph body.
- Preserve the user-owned untracked `prompt/anthropic-skills/` directory.

---

### Task 1: Add OpenAI Responses support and Luna defaults

**Files:**
- Modify: `backend/config.py`
- Modify: `.env.example`
- Modify: `backend/requirements.runtime.txt`
- Modify: `backend/services/llm_client.py`
- Modify: `backend/services/reference_pdfs.py`
- Modify: `backend/tests/test_llm_client.py`
- Modify: `backend/tests/test_reference_pdfs.py`

**Interfaces:**
- `LLMClient(provider: str | None = None, model: str | None = None, timeout_ms: int = 60_000)`
- Existing `generate`, `generate_multimodal`, `upload_pdf`, and `delete_file` methods remain available.
- Defaults become `provider="openai"` and `model="gpt-5.6-luna"`.

- [ ] Write failing tests asserting OpenAI/Luna defaults and Responses API request construction.
- [ ] Write failing tests for Pydantic structured output, token usage, reasoning tokens, incomplete responses, ordered PDF inputs, file cleanup, and transient OpenAI errors.
- [ ] Run `python -m pytest backend/tests/test_llm_client.py backend/tests/test_reference_pdfs.py -v` and confirm the new tests fail against the Gemini-only client.
- [ ] Add `OPENAI_API_KEY`, set `LLM_PROVIDER=openai`, set `LLM_MODEL=gpt-5.6-luna`, and remove the mistakenly introduced `ASSESSMENT_GENERATION_PATH` setting because question routing is unchanged.
- [ ] Add `openai>=1.108.0,<3` to runtime requirements.
- [ ] Implement an OpenAI adapter using `responses.create` for text and `responses.parse(..., text_format=response_schema)` for structured output while retaining the Google adapter for explicit legacy overrides.
- [ ] Add provider identity to serialized `ProviderFileAttachment`, defaulting missing legacy values to `google`.
- [ ] Map OpenAI response IDs, model versions, input/output totals, cached tokens, reasoning tokens, incomplete reasons, and retryable SDK exceptions into existing application contracts.
- [ ] Run the focused tests and confirm they pass.
- [ ] Commit with:

```powershell
git add .env.example backend/config.py backend/requirements.runtime.txt backend/services/llm_client.py backend/services/reference_pdfs.py backend/tests/test_llm_client.py backend/tests/test_reference_pdfs.py
git commit -m "Add GPT-5.6 Luna provider support" -m "Route the existing LLM client contract through OpenAI Responses by default while retaining Google compatibility, structured output, attachments, usage accounting, and retry behavior."
```

### Task 2: Preserve actual-prompt-driven assessment generation on Luna

**Files:**
- Modify: `backend/workers/assessment_worker.py`
- Modify: `backend/workers/evaluation_worker.py`
- Modify: `backend/services/run_service.py`
- Modify: `backend/tests/test_worker.py`
- Modify: `backend/tests/test_evaluation_worker.py`
- Modify: `backend/tests/test_run_service.py`

**Interfaces:**
- Assessment worker constructs `LLMClient(provider=run.provider, model=run.model)`.
- Evaluation worker constructs `LLMClient(provider=settings.llm_provider, model=settings.llm_evaluation_model or settings.llm_model)`.
- Actual-prompt preparation and `Prompt` persistence remain unchanged.

- [ ] Add a failing worker test asserting the established call sequence remains actual-prompt preparation followed by assessment generation, with the assessment call receiving `prompt.execution_system_prompt` and returning the current JSON contract.
- [ ] Add a failing Anthropic-structure test asserting its actual-prompt compiler call and assessment call both use the run's Luna client.
- [ ] Add a failing repair test asserting invalid assessment JSON is repaired by the same Luna client and the repaired JSON remains the persisted canonical assessment.
- [ ] Add evaluator and execution-snapshot tests for `openai` and `gpt-5.6-luna`.
- [ ] Run `python -m pytest backend/tests/test_worker.py backend/tests/test_evaluation_worker.py backend/tests/test_run_service.py -v` and confirm routing tests fail.
- [ ] Pass both provider and model when constructing worker clients; do not branch around actual-prompt preparation.
- [ ] Keep the OpenAI local actual-prompt template route and Anthropic provider-compiled route exactly as implemented, changing only provider/model plumbing.
- [ ] Run the focused tests and confirm they pass.
- [ ] Commit with:

```powershell
git add backend/workers/assessment_worker.py backend/workers/evaluation_worker.py backend/services/run_service.py backend/tests/test_worker.py backend/tests/test_evaluation_worker.py backend/tests/test_run_service.py
git commit -m "Run assessment stages on Luna" -m "Use GPT-5.6 Luna for actual-prompt compilation where applicable, assessment JSON generation, repair, and evaluation without changing the established actual-prompt-driven JSON workflow."
```

### Task 3: Implement the Luna Code Interpreter DOCX provider

**Files:**
- Create: `backend/prompts/luna_direct_docx_system.md`
- Create: `backend/services/luna_direct_docx_provider.py`
- Create: `backend/tests/test_luna_direct_docx_provider.py`

**Interfaces:**
- `LunaDirectDocxProvider.generate(assessment_json: dict, *, run_id: int) -> LunaDocxResult`
- `LunaDocxResult` contains `content: bytes`, `provider_result: LLMResult`, `container_id: str`, `file_id: str`, `filename: str`, and `prompt_sha256: str`.
- The provider must not import or execute LibreOffice-related services.

- [ ] Write a failing test that mocks `client.containers.create(...)`, `client.responses.create(...)`, the returned `container_file_citation`, and `client.containers.files.content.retrieve(...)`.
- [ ] Assert the Responses request uses model `gpt-5.6-luna`, a required `code_interpreter` tool, the created container ID, and canonical JSON serialized deterministically.
- [ ] Assert exactly one `.docx` citation is required; zero, multiple, or non-DOCX citations raise a safe `LunaDocxGenerationError`.
- [ ] Assert the generated file is downloaded before best-effort container cleanup.
- [ ] Run `python -m pytest backend/tests/test_luna_direct_docx_provider.py -v` and confirm failure because the provider does not exist.
- [ ] Add a bounded authoring prompt requiring Luna to create `/mnt/data/assessment.docx`, preserve assessed text exactly, create editable native Word equations, include questions and solutions, avoid external resources, and cite the completed file once.
- [ ] Implement explicit 1 GB container creation, a required Code Interpreter response, citation extraction, immediate byte download, maximum file-size enforcement, and best-effort container deletion.
- [ ] Reject empty content, non-ZIP bytes, filenames without `.docx`, responses without a completed status, and files above the configured maximum artifact size.
- [ ] Run the provider tests and confirm they pass.
- [ ] Commit with:

```powershell
git add backend/prompts/luna_direct_docx_system.md backend/services/luna_direct_docx_provider.py backend/tests/test_luna_direct_docx_provider.py
git commit -m "Generate DOCX files with Luna" -m "Add a bounded Code Interpreter provider that turns canonical assessment JSON into a downloadable DOCX, captures provider provenance, and cleans up its ephemeral OpenAI container."
```

### Task 4: Verify Luna-generated DOCX without LibreOffice

**Files:**
- Create: `backend/services/luna_direct_docx_verifier.py`
- Create: `backend/tests/test_luna_direct_docx_verifier.py`
- Reuse: `backend/services/docx_package_verifier.py`
- Reuse: `backend/services/docx_manifest_verifier.py` where compatible

**Interfaces:**
- `LunaDirectDocxVerifier.verify(content: bytes, assessment_json: dict) -> VerificationReport`
- Verification performs package, XML, canonical-content, and OMML checks only.

- [ ] Create fixture DOCX bytes containing one question, one solution, and one OMML equation using `python-docx` plus bounded XML insertion.
- [ ] Write failing tests for a valid package, corrupt ZIP, missing main document, missing question text, missing solution text, unresolved `[[EQ:...]]` placeholders, and missing OMML for an assessment with equations.
- [ ] Run `python -m pytest backend/tests/test_luna_direct_docx_verifier.py -v` and confirm failure because the verifier does not exist.
- [ ] Implement ZIP/package checks, safe XML parsing, exact normalized containment checks for canonical question and solution text, placeholder rejection, and `m:oMath`/`m:oMathPara` presence checks.
- [ ] Return stable safe issue codes such as `docx_package_invalid`, `canonical_question_missing`, `canonical_solution_missing`, `equation_placeholder_unresolved`, and `native_equation_missing`.
- [ ] Do not call `DocxVisualRenderer`, `DocxRenderVerifier`, the LibreOffice command, or PDF/image rendering.
- [ ] Run the verifier tests and confirm they pass.
- [ ] Commit with:

```powershell
git add backend/services/luna_direct_docx_verifier.py backend/tests/test_luna_direct_docx_verifier.py
git commit -m "Verify Luna DOCX artifacts structurally" -m "Validate generated Word packages against canonical assessment content and native-equation requirements without invoking LibreOffice or adding visual rendering to the experimental path."
```

### Task 5: Register `luna_direct` as the default document backend

**Files:**
- Modify: `backend/config.py`
- Modify: `.env.example`
- Modify: `backend/services/document_generators.py`
- Modify: `backend/schemas/run_schema.py`
- Modify: `backend/tests/test_document_generators.py` if present, otherwise create it
- Modify: `backend/tests/test_worker.py`
- Modify: `backend/tests/test_api_runs.py`

**Interfaces:**
- `DOCX_GENERATION_BACKEND` accepts `luna_direct`, `legacy`, `self_hosted_code`, and `agentic_tools`.
- `LunaDirectDocumentGenerator.generate(...) -> DocumentGenerationResult` uses Tasks 3 and 4.
- Existing registry lookup remains `document_generator_registry.get(name)`.

- [ ] Add failing configuration and registry tests asserting `luna_direct` is the default and all four backends are resolvable.
- [ ] Add a failing successful-pipeline test asserting validated assessment JSON is sent to the Luna provider, verified, saved through `generated_docx_artifact`, and marked canonical without any LibreOffice-related mock being called.
- [ ] Add failing tests for provider failure and structural verification failure; both must leave the original assessment available and produce safe rewrite failure codes.
- [ ] Run the focused configuration, registry, worker, and API tests and confirm failure.
- [ ] Extend the backend literal, set `.env.example` to `DOCX_GENERATION_BACKEND=luna_direct`, and register `LunaDirectDocumentGenerator` alongside the three existing generators.
- [ ] Record the Luna DOCX call through `record_model_call` using a dedicated allowed stage such as `docx_direct_generation`; add the required database check-constraint migration and migration test if the stage constraint rejects it.
- [ ] Persist the downloaded bytes using the existing artifact and assessment-version services without modifying canonical assessment JSON.
- [ ] Ensure progress messages identify Luna DOCX generation and structural verification rather than LibreOffice rendering.
- [ ] Run focused tests and confirm they pass.
- [ ] Commit with:

```powershell
git add .env.example backend/config.py backend/services/document_generators.py backend/schemas/run_schema.py backend/tests/test_document_generators.py backend/tests/test_worker.py backend/tests/test_api_runs.py backend/migrations/versions
git commit -m "Make Luna direct DOCX the branch default" -m "Register the Code Interpreter document backend as the default experimental path while preserving every existing backend and keeping the validated assessment JSON as canonical content."
```

### Task 6: Confirm every LLM call uses Luna and run the full test pipeline

**Files:**
- Modify: `backend/services/gemini_docx_authoring.py`
- Modify: `backend/services/gemini_docx_tool_agent.py`
- Modify: `backend/services/docx_authoring_pipeline.py`
- Modify: `backend/services/document_generators.py`
- Modify: related DOCX tests
- Modify: `README.md`

**Interfaces:**
- Dedicated legacy DOCX LLM adapters use `provider="openai"`, `model="gpt-5.6-luna"` when those alternative backends are selected.
- Historical database values and intentionally explicit Google compatibility tests remain unchanged.

- [ ] Update dedicated DOCX authoring and agentic-tool model constants to `gpt-5.6-luna` and provider provenance to `openai`.
- [ ] Update tests for DOCX program generation, repair, design, and visual review to assert Luna routing when those retained backends are selected.
- [ ] Run `rg -n -S 'gemini-3\.5-flash-lite|provider="google"|provider = "google"|LLMClient\(' backend -g '*.py'` and classify every remaining result as Google-adapter compatibility, historical data, or an error to fix.
- [ ] Document the experimental pipeline and its lack of visual rendering, including `OPENAI_API_KEY`, `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-5.6-luna`, and `DOCX_GENERATION_BACKEND=luna_direct`.
- [ ] Run `python -m pytest backend/tests -v`; require all unit tests to pass, allowing only environment-dependent PostgreSQL skips.
- [ ] Run `npm test -- --run` in `frontend`; require PASS.
- [ ] Run `npm run build` in `frontend`; require PASS.
- [ ] Run `git diff --check`; require no whitespace errors.
- [ ] Confirm `git status --short --branch` shows only intended tracked changes plus preserved `prompt/anthropic-skills/`.
- [ ] Commit with:

```powershell
git add backend/services/gemini_docx_authoring.py backend/services/gemini_docx_tool_agent.py backend/services/docx_authoring_pipeline.py backend/services/document_generators.py backend/tests README.md
git commit -m "Complete the Luna pipeline experiment" -m "Align retained LLM-backed document paths with GPT-5.6 Luna, document the direct-DOCX experiment and validation tradeoffs, and verify backend and frontend behavior end to end."
```

## Expected Experimental Pipeline

```text
Experiment inputs
  -> existing actual-prompt creation
  -> GPT-5.6 Luna assessment JSON generation
  -> existing JSON validation and Luna repair when needed
  -> persist canonical assessment JSON
  -> second GPT-5.6 Luna call with Code Interpreter
  -> download generated DOCX immediately
  -> structural/content/OMML verification without LibreOffice
  -> persist DOCX artifact
  -> GPT-5.6 Luna evaluation
```

## Self-Review Results

- The plan no longer bypasses the actual prompt.
- The current assessment JSON remains canonical and unchanged by document generation.
- The second Luna call creates the DOCX as requested.
- LibreOffice is excluded from the new default backend.
- Existing document backends remain in the registry.
- All LLM-backed production paths are explicitly covered by the Luna migration and verification tasks.

