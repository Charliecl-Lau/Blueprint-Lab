# Flat Provider Math Contract and Timeout Design

## Problem

Assessment generation sends Gemini the complete recursive `MathNode` JSON
Schema. A plain request and a flat-schema request return normally, while the
recursive assessment schema does not return before a 30-second diagnostic
timeout. Production currently configures no provider timeout, so the worker can
remain in `generating` without receiving response metadata or token usage.

The database migration and `concept_map_bridge` metadata are not on the failing
schema path. The failure was introduced when the provider-facing schema changed
from a flat contract to the canonical recursive Pydantic schema.

## Goals

- Prevent Gemini structured-output requests from receiving a recursive schema.
- Preserve native rendering for subscripts such as `x_A` and `x_B`, combined
  scripts, fractions, radicals, and signed superscripts.
- Keep the canonical Pydantic assessment contract and internal `MathNode` AST.
- Bound provider calls so a stalled request becomes a visible, retryable error.
- Preserve database, traceability, grading, evaluation, and export behavior.

## Provider Contract

The Gemini response schema will contain only flat question content:

- `body` and `model_answer` remain strings.
- Equation references continue to use `[[EQ:<label>]]`.
- Each equation requires `label`, `expression`, and `location`.
- Provider-facing equation objects do not expose `math`.
- Provider-facing questions do not expose `body_segments`,
  `model_answer_segments`, or option `segments`.
- The provider schema retains all required assessment metadata, options,
  quality checks, and revision options.

The provider contract will be generated from dedicated flat Pydantic provider
models. It will not mutate or weaken the canonical application models.

## Application Data Flow

1. The worker sends Gemini the flat provider schema.
2. Gemini returns linear equation expressions such as
   `x_A + x_B = 1`.
3. The response is validated against the flat provider contract.
4. Each expression is deterministically parsed into a `MathNode`.
5. The normalized payload is validated with
   `AssessmentGenerationResponse`.
6. The application stores both the original `expression` and generated `math`
   AST for traceability and rendering.
7. Existing persistence, grading, evaluation, frontend MathML, and DOCX export
   consume the canonical assessment payload.

The same normalization runs after assessment-repair responses.

## Math Compatibility

The deterministic parser must preserve:

- `x_A` and `x_B` as subscript nodes.
- `x_A^2` as combined subscript and superscript nodes.
- `DeltaH/(T DeltaS)` as a fraction.
- `sqrt(x_A)` as a radical.
- Signed superscripts such as `K^-1`.

If an expression is outside the supported grammar, parsing falls back to an
editable text math node. The original expression remains available. Provider
output is never discarded solely because the parser cannot structure an
unfamiliar expression.

Matrices are not added to the linear grammar in this change. Existing
canonical matrix AST support remains available for stored or
application-produced payloads, but Gemini will not generate matrix ASTs through
structured output.

## Provider Timeout and Failure State

`LLMClient` will create the Google Gen AI client with a 60-second HTTP timeout.
This applies to prompt generation, assessment generation, repair, and
evaluation calls using the shared client.

On timeout:

- The worker records a failed model call without token counts because no
  provider response exists.
- The run records the stage-specific provider error.
- Existing bounded Celery retry behavior remains in effect.
- The API exposes the error state instead of leaving the request blocked
  indefinitely.

No speculative token counts will be created for failed calls.

## Testing

Automated tests will prove:

- The provider schema contains no recursive math definitions or references.
- Provider equations require a non-empty linear `expression`.
- Flat generated equations are normalized into canonical ASTs.
- `x_A`, `x_B`, combined scripts, fractions, radicals, and signed
  superscripts survive normalization.
- Canonical models remain strict for directly supplied malformed ASTs.
- The configured Google client receives a 60-second timeout.
- Worker generation and repair continue using the provider schema and persist
  canonical normalized payloads.
- Existing backend and frontend test suites continue to pass.

## Non-Goals

- No database migration.
- No changes to concept-bridge behavior or metadata.
- No UI workflow changes.
- No replacement of the internal `MathNode` model.
- No new matrix-expression grammar.
