# Native Word OMML Equations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate assessment DOCX files whose displayed and embedded mathematics is represented as editable, built-up Microsoft Word OMML instead of plain equation strings.

**Architecture:** Preserve plain `body` and `model_answer` strings for the application UI, while adding structured text/math segment arrays for deterministic DOCX rendering. Represent each mathematical expression as a validated recursive JSON AST and serialize its nodes directly to semantic OMML.

**Tech Stack:** Python 3, Pydantic 2, python-docx, OOXML/OMML, pytest

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
