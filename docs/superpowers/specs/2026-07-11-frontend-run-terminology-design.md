# Frontend Run Terminology Design

## Goal

Move the frontend to immutable run terminology while accepting legacy generation-shaped backend responses during the transition. A retry must add and select a new run without removing the original result from comparison history.

## Architecture

Canonical run types, API methods, store fields, and page labels will be used throughout the frontend. Compatibility will be confined to boundaries: experiment API responses normalize `generations` to `runs`, SSE input normalizes `generation_id` to `run_id`, and the deprecated generation API delegates to the run API. `Generation` remains only as a temporary type alias for `Run`.

## Components and Data Flow

- `types/index.ts` defines `Run`, `RunSource`, `PromptProvenance`, and `AssessmentOutput`.
- `api/runs.ts` owns canonical retrieval, retry, and DOCX export calls.
- `api/generations.ts` delegates legacy calls to `runsApi`.
- `api/experiments.ts` normalizes legacy response fields once before returning data.
- `runStore.ts` indexes runs by ID, applies normalized progress events, and adds retry results without replacing prior runs.
- Progress and viewer pages display condition codes and run numbers and use canonical run actions.

## Compatibility and Errors

Legacy `generation_id` SSE events and experiment responses containing only `generations` remain accepted. Canonical fields take precedence when both forms are present. Existing API error propagation remains unchanged; this task does not introduce new retry or notification behavior.

## Testing

Store tests will prove immutable retry history and SSE normalization. Application tests will exercise compatibility normalization and run-oriented rendering. The full Vitest suite and production TypeScript build must pass.

## Scope

This task changes frontend terminology and state behavior only. Backend compatibility removal, new comparison UI, and Stage 2 evaluation features are outside scope.
