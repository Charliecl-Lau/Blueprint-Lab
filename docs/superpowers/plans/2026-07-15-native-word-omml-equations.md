# Native Word OMML Equations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate assessment DOCX files whose displayed and embedded mathematics is represented as editable, built-up Microsoft Word OMML instead of plain equation strings.

**Architecture:** Preserve plain `body` and `model_answer` strings for the application UI, while adding structured text/math segment arrays for deterministic DOCX rendering. Represent each mathematical expression as a validated recursive JSON AST and serialize its nodes directly to semantic OMML.

**Tech Stack:** Python 3, Pydantic 2, python-docx, OOXML/OMML, pytest

## Live Gemini integration findings (2026-07-16)

The recursive provider-schema approach is disabled. A live request to
`gemini-3.1-flash-lite` using the recursive math AST failed during provider-side
schema processing before assessment generation began. Run 18 made four
assessment attempts, and every attempt returned HTTP 500 with:

> Limits exceeded while trying to flatten schema. Schema is too complex to process.

The recursive contract contained 13 discriminated math-node variants and 17
self-references through `$defs/mathNode`, used by question-body segments,
model-answer segments, answer-option segments, and displayed equations. Local
Pydantic validation and mocked SDK tests did not reveal the provider's schema
flattening limit.

`ASSESSMENT_PROVIDER_SCHEMA` has therefore been restored exactly to the flat
schema on `main`, with no `$defs`, `$ref`, or `oneOf`. Live run 19 then completed
successfully with two Gemini calls, proving that the recursive provider contract
was the blocker.

The flat-schema run also proved that prompt instructions alone do not produce
native Word equations in the current pipeline. Run 19 stored
`body_segments = null`, `model_answer_segments = null`, and `equations = []`;
all mathematical expressions remained in the plain `body` and `model_answer`
strings. Because `docx_exporter.py` only invokes the OMML serializer when those
structured fields contain math nodes, the exported DOCX contains plain text for
this run.

Current conclusion:

- Do not send the recursive math AST as the Gemini provider response schema.
- Prompt-only requests are insufficient for deterministic OMML generation when
  the provider schema exposes only the flat main-branch fields.
- A future implementation needs a bounded, non-recursive provider format or a
  separately designed equation-conversion stage. Do not add heuristic parsing
  of arbitrary generated text without an explicit design decision.

### Flat equation-entry experiment

The next live experiment keeps the main assessment schema flat while adding one
optional, non-recursive `equations` array to each question. Each entry contains
only `label`, `expression`, and `location`; `expression` uses Microsoft Word
linear equation notation, and `location` is `question` or `solution`. The schema
contains no `$defs`, `$ref`, or `oneOf`. The generation prompt requires one such
entry for every mathematical expression and treats mathematical content with an
empty equation array as invalid.

The backend converts these flat entries into an editable `<m:oMath>` container
during DOCX export. A bounded Word-linear parser converts `/` fractions, `_`
subscripts, `^` superscripts, combined scripts, and `sqrt(...)` or `√(...)`
radicals into semantic `<m:f>`, `<m:sSub>`, `<m:sSup>`, and `<m:rad>` OMML.
Malformed or unsupported expressions fall back to editable OMML text instead of
breaking document export. This experiment tests whether Gemini reliably
populates the flat equation array using that supported notation.

Equation placement uses explicit `[[EQ:label]]` placeholders. Gemini must replace
each mathematical expression in a question body, answer option, or model answer
with a placeholder whose unique ASCII label matches an `equations[]` entry. The
DOCX exporter replaces the placeholder in place with OMML and tracks the rendered
label so it is not emitted again as a standalone equation paragraph. Unreferenced
legacy equation entries continue to render separately for backward compatibility.

## Global Constraints

- Do not use LaTeX, MathML conversion, images, screenshots, Microsoft Word automation, or heuristic equation parsing in production.
- Preserve plain string fields as readable application and historical-data fallbacks.
- Render embedded math in question bodies, answer options, and model answers through mixed text/math segments.
- Serialize structured math deterministically so identical JSON produces identical OMML.
- Commit messages must contain a subject and explanatory paragraph body, with no attribution trailers.

---

### Task 1: Define and require the structured math contract

**Files:**
- Modify: `backend/schemas/assessment_schema.py`
- Modify: `backend/services/actual_prompt.py`
- Modify: `backend/services/structure_system_prompts.py`
- Test: `backend/tests/test_assessment_schema.py`
- Test: `backend/tests/test_actual_prompt.py`

- [x] Add failing tests for recursive equation ASTs, malformed nodes, embedded content segments, provider-schema coverage, and prompt requirements.
- [x] Define discriminated recursive node types for text, symbols, numbers, operators, sequences, equations, fractions, differentials, products, scripts, radicals, and matrices.
- [x] Add mixed text/math segment fields for question bodies, options, and model answers.
- [x] Require structured math in the fixed generation prompt and both prompt-compiler variants.
- [x] Route recursive `$defs` schemas through Gemini's JSON Schema configuration field.

### Task 2: Serialize structured math into semantic OMML

**Files:**
- Create: `backend/services/omml.py`
- Modify: `backend/services/docx_exporter.py`
- Test: `backend/tests/test_docx_exporter.py`

- [x] Add a failing thermodynamic-equation regression test based on `dP/dT = Delta H / (T * Delta V)`.
- [x] Implement deterministic OMML runs, fractions, scripts, radicals, matrices, equations, sequences, products, and differentials.
- [x] Render mixed text/math segments inside bodies, options, and model answers.
- [x] Retain legacy linear strings only as a historical-data fallback.

### Task 3: Verify the pipeline and artifact

**Files:**
- Modify: `backend/tests/test_generator.py`
- Modify: `backend/tests/test_worker.py`
- Modify: `backend/tests/test_llm_client.py`

- [x] Verify structured AST preservation through generation parsing.
- [x] Verify the worker sends the recursive provider schema.
- [x] Run the complete backend suite.
- [x] Inspect generated `word/document.xml` for semantic OMML structures.
- [x] Verify the generated artifact manually in Microsoft Word; the user confirmed that Word displays it as a native equation.
