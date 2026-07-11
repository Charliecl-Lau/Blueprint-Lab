# Research Database Foundation Design

**Date:** 2026-07-11
**Status:** Approved

## Purpose

Blueprint Lab will evolve from an assessment-generation application into an auditable research logging platform. Stage 1 establishes reproducible, immutable generation records and complete prompt and source-document provenance. Normalized rubric evaluation, rater management, and criterion-level scoring are deferred to Stage 2.

The central invariant is:

> Every generated assessment must be traceable to its experiment, condition, exact prompt, model settings, source-document versions, raw provider response, and parsed output.

## Scope

Stage 1 includes:

- PostgreSQL as the default runtime database.
- SQLite support for fast unit tests.
- Alembic-managed schema migrations.
- A formal rename from `generations` to immutable `runs`.
- Temporary compatibility aliases for existing generation API consumers.
- Complete model and sampling-setting capture.
- Exact system and user prompt persistence with hashes and version metadata.
- First-class assessment output records containing raw and parsed output.
- Source-document metadata, extracted text, SHA-256 hashes, and immutable file snapshots.
- Explicit associations between runs and the source documents used by them.
- Migration of existing generation data without loss.

Stage 1 does not include:

- Rubric definitions or rubric version management.
- Rater profiles, blinding workflows, or training records.
- Evaluation rounds or criterion-level evaluation scores.
- Inter-rater reliability analysis.
- Authentication or multi-tenant authorization.
- Object storage, pgvector, RAG, or document retrieval.

Those evaluation features form a separate Stage 2 design and implementation plan.

## Integration Strategy

Use an incremental compatibility migration. Introduce the research-domain schema and migrate existing data while preserving temporary compatibility at the API boundary. New code uses `run` terminology; compatibility routes and response aliases allow the current frontend to continue working during the transition.

This approach avoids duplicate long-lived generation and run concepts, preserves existing records, and limits frontend and worker disruption. Compatibility behavior is explicitly transitional and emits deprecation metadata where practical.

## Domain Model

```text
Experiment
  └── Condition
        └── Run
              ├── Prompt
              ├── Assessment
              ├── RunSourceDocument
              │     └── SourceDocument
              └── DocumentArtifact
```

### Experiment

An experiment groups conditions and states the research purpose.

Required fields:

- `id`
- `name`
- `description`
- `course`
- `topic_area`
- `research_question`
- `status`
- `created_at`
- `updated_at`

Existing experiment fields required by prompt generation, including learning objectives, assessment type, difficulty, question count, and estimated completion time, remain available. `status` is constrained to `draft`, `active`, `completed`, or `archived`.

### Condition

A condition is a stable experimental treatment within an experiment.

Add:

- `condition_code`, unique within an experiment.
- `bloom_level_enabled`.
- `factor_configuration`, a JSON snapshot of all factor flags and values.
- `created_at`.

Existing explicit Boolean factor columns remain because they support direct factorial queries. The JSON snapshot provides forward compatibility for new factors and captures the exact configuration used when the condition was created.

Condition records are not mutated after a run exists. A changed factor configuration creates a new condition and condition code.

### Run

`Run` replaces `Generation` as the canonical research term. One run represents one immutable model sampling attempt under one condition.

Required fields:

- `id`
- `experiment_id`
- `condition_id`
- `run_number`
- `status`
- `model_provider`
- `model_name`
- `model_version`
- `temperature`
- `top_p`
- `seed`
- `max_output_tokens`
- `model_settings`, containing the canonical request settings JSON.
- `provider_request_id`
- `generation_time_ms`
- `finish_reason`
- `error_type`
- `error_message`
- `created_at`
- `started_at`
- `completed_at`

`(condition_id, run_number)` is unique. Run numbers are allocated transactionally. Status is constrained to `pending`, `prompting`, `generating`, `documenting`, `complete`, or `error`.

A failed run is retained. Retrying or regenerating creates a new run with the next run number. Normal application operations never clear or overwrite a completed or failed run's prompt, output, sources, or artifacts.

### Prompt

Each run has exactly one prompt record containing the effective request inputs.

Required fields:

- `id`
- `run_id`, unique.
- `prompt_structure`
- `system_prompt`
- `final_prompt`
- `prompt_template_version`
- `prompt_generator_version`
- `prompt_hash`
- `created_at`

`prompt_hash` is SHA-256 over a canonical UTF-8 JSON envelope containing the system prompt, final prompt, prompt structure and version, canonical model settings, and ordered source-document hashes. JSON is serialized with sorted keys and compact separators before hashing.

### Assessment

Each run has at most one assessment output. Failed runs may have no assessment.

Required fields:

- `id`
- `run_id`, unique.
- `raw_response`
- `parsed_output`, stored as JSON.
- `output_hash`
- `schema_version`
- `created_at`

`output_hash` is SHA-256 of the exact UTF-8 raw provider response. The raw response is persisted before parsing. Parse or schema-validation failures mark the run as `error` while retaining the raw response for diagnosis.

The existing question-level model `quality_check` remains part of `parsed_output`. It is model self-evaluation metadata and is not an independent rubric evaluation.

### SourceDocument

A source document represents one immutable file version available for prompting.

Required fields:

- `id`
- `name`
- `document_type`
- `version`
- `original_filename`
- `media_type`
- `content`
- `content_hash`
- `extracted_text`
- `extraction_method`
- `description`
- `uploaded_at`

`content` stores the immutable original file bytes in PostgreSQL for Stage 1. `content_hash` is the SHA-256 hash of those exact bytes. A changed file creates a new source-document record rather than updating the prior snapshot.

Uploads have explicit size and media-type validation. Stage 1 supports the document types already used by the prompt workflow; unsupported files are rejected before persistence. The initial maximum file size is 20 MiB per document.

### RunSourceDocument

This association records the exact sources used by a run.

Required fields:

- `run_id`
- `source_document_id`
- `role`
- `ordinal`
- `included_text_hash`
- `created_at`

`role` is constrained to `course_syllabus`, `bridge_map`, `few_shot_example`, `rubric`, `reference_content`, or `instructor_example`. `ordinal` preserves prompt assembly order. `included_text_hash` identifies the exact extracted text included in the run if it differs from the entire stored extraction.

### DocumentArtifact

Existing DOCX artifacts remain associated one-to-one with a run. Artifacts include filename, media type, bytes, content hash, and creation time. Regeneration produces a new run and artifact instead of replacing the prior artifact.

## Data Flow

1. A researcher creates or selects an experiment and immutable condition.
2. The API creates a pending run with the next transactional `run_number`.
3. Selected source-document snapshots are associated with the run in prompt order.
4. The worker builds the exact system and final prompts from the persisted condition and sources.
5. The worker stores the prompt and reproducibility hash before calling the model.
6. The model client receives explicit sampling settings from the run's canonical settings snapshot.
7. The worker persists the raw provider response before parsing it.
8. Valid parsed output is stored as the assessment; invalid output leaves diagnostic evidence and marks the run as errored.
9. A DOCX artifact is generated from the persisted assessment and associated with the run.
10. Progress events report the run ID, condition ID, run number, and stage.

## API Design

Canonical routes use `/runs`:

- `POST /conditions/{condition_id}/runs` creates a new immutable run.
- `GET /runs/{run_id}` returns run metadata, prompt, assessment, source summaries, and artifact availability.
- `POST /runs/{run_id}/retry` creates and enqueues a new run under the same condition.
- `GET /runs/{run_id}/export-docx` returns that run's immutable artifact.
- Source-document creation and retrieval use `/source-documents`.

The existing `/generations/{id}` read and export routes remain temporary aliases. Existing regenerate behavior changes semantics: it creates a new run and returns the new run ID instead of deleting data. Compatibility responses may include both `run_id` and deprecated `generation_id` fields during the transition.

API responses never include stored source file bytes unless a dedicated download endpoint is called. Rater-facing blinding is deferred to Stage 2.

## Database and Migration Strategy

PostgreSQL becomes the documented and configured runtime default. SQLite remains supported for unit tests, so core models and repository behavior must not rely on PostgreSQL-only SQL in ordinary test paths.

Alembic becomes the authoritative schema manager. Application startup no longer calls `Base.metadata.create_all()` in managed runtime environments. Tests may continue creating isolated schemas directly from metadata.

The migration sequence is:

1. Add Alembic and baseline the current schema.
2. Rename `generations` to `runs` and rename its foreign keys without dropping records.
3. Add reproducibility columns and populate deterministic defaults for legacy rows.
4. Rename `prompt_records` to `prompts` and expand its provenance fields.
5. Move `generated_json` into first-class assessment rows.
6. Add source-document and association tables.
7. Add hashes and artifact metadata.
8. Add uniqueness, check constraints, and indexes after backfill.

Legacy records are marked through version metadata such as `prompt_generator_version="legacy-unknown"` and nullable provider settings where historical values cannot be reconstructed. The migration never fabricates seeds or sampling values.

## Error Handling and Immutability

- File validation failures return a client error and create no source-document row.
- Prompt construction failures retain the run and mark it `error`.
- Provider failures retain settings, prompt, source associations, and sanitized error metadata.
- Raw model responses are stored before parsing so malformed output remains inspectable.
- Artifact failures retain the completed assessment but mark the run `error` at the documenting stage; retry creates a new run.
- Database uniqueness conflicts during run-number allocation are retried transactionally.
- Delete endpoints for runs, prompts, assessments, and used source snapshots are not provided in Stage 1.
- API keys, authorization headers, and provider credentials are never persisted in model settings or error messages.

## Testing Strategy

Unit tests continue to use SQLite and cover:

- Model relationships and constraints that SQLite can enforce.
- Canonical prompt and output hashing.
- Model-settings serialization.
- Run creation and immutable retry behavior.
- Raw-response retention after parse failure.
- Source upload validation, hashing, snapshots, and run associations.
- Compatibility route behavior.
- Worker persistence ordering and error transitions.

PostgreSQL integration tests cover:

- Alembic upgrade from the current schema to head.
- Existing generation-data preservation.
- Table and column renames.
- Check constraints, unique constraints, foreign keys, and transactional run numbering.
- Migration downgrade only where it can be performed without destroying research records; irreversible data-shape migrations are documented as such.

End-to-end API tests confirm that creating a run, generating an assessment, retrieving its provenance, retrying it, and exporting each artifact leaves both runs intact.

## Operational and Security Considerations

- Database URLs and credentials are provided through environment configuration.
- PostgreSQL backups include source snapshots and artifacts because they are part of the research record.
- Source and output sizes are bounded to prevent unbounded database growth.
- User-facing errors contain stable error codes and omit provider secrets.
- Hashes support integrity checking, not authenticity; signed records and external archival storage are outside Stage 1.

## Success Criteria

Stage 1 is complete when:

- A fresh PostgreSQL database can be created exclusively through Alembic.
- An existing database can migrate without losing generation records, prompts, outputs, or artifacts.
- New code uses `Run` as the canonical research entity.
- Retrying or regenerating never overwrites an earlier attempt.
- Every completed run exposes its exact prompts, canonical model settings, source-document hashes and snapshots, raw response, parsed assessment, and output hashes.
- The existing frontend remains usable through the compatibility layer during migration.
- SQLite unit tests and PostgreSQL migration/integration tests pass.
- No evaluation or rater functionality is implicitly mixed into model self-quality checks.

## Stage 2 Boundary

Stage 2 will add versioned rubrics, rubric criteria, raters, blinded evaluation assignments, evaluation rounds, criterion-level scores, comments, and analysis-ready exports. Stage 2 will reference `assessments.id`; it will not require changing the immutable run and provenance model established here.
