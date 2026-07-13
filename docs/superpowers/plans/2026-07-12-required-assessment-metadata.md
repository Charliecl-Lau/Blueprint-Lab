# Required Assessment Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject generated questions unless they contain all requested assessment metadata, at least one quality check, and two or three revision options.

**Architecture:** Keep Pydantic validation and Gemini's provider JSON schema aligned in `assessment_schema.py`. Tests exercise both runtime validation and the provider contract before production code changes.

**Tech Stack:** Python, Pydantic, pytest, Gemini response JSON schema

## Global Constraints

- Every question requires metadata, quality checks, and revision options.
- Metadata requires question title, question type, difficulty, assessment setting, MSE202 concepts, MSE302 concepts, concept-map bridge, and materials-science context.
- Concept lists and quality checks must be non-empty.
- Revision options must contain two or three entries.
- Do not commit changes; the user is the sole commit author.

---

### Task 1: Enforce the complete assessment response contract

**Files:**
- Modify: `backend/schemas/assessment_schema.py`
- Test: `backend/tests/test_assessment_schema.py`
- Test: `backend/tests/test_worker.py`

**Interfaces:**
- Consumes: `AssessmentGenerationResponse.model_validate(dict)` and `ASSESSMENT_PROVIDER_SCHEMA`
- Produces: strict `QuestionMetadata` and `QuestionResponse` validation plus an aligned provider schema

- [ ] **Step 1: Write failing model-validation tests**

Create a complete question payload and assert that removing each required metadata field raises `pydantic.ValidationError`. Also assert empty MSE concept lists, empty quality checks, and revision-option counts of one and four are rejected.

- [ ] **Step 2: Write a failing provider-schema test**

Assert that the provider question schema requires `type`, `body`, `metadata`, `quality_check`, and `revision_options`; that metadata requires all eight requested fields; and that array bounds match the application validation.

- [ ] **Step 3: Run tests and verify contract failures**

Run: `python -m pytest backend/tests/test_assessment_schema.py backend/tests/test_worker.py -q`

Expected: FAIL because metadata fields currently have defaults and the provider schema omits metadata, quality checks, and revision options.

- [ ] **Step 4: Implement strict Pydantic fields**

Add required `question_type`, remove defaults from the eight requested metadata fields, use `Field(min_length=1)` for both concept lists, require `metadata`, and constrain `quality_check` to at least one entry and `revision_options` to two or three entries.

- [ ] **Step 5: Expand the provider JSON schema**

Define metadata, quality-check, and revision-option properties with matching required fields and array bounds. Require these properties on every provider question object.

- [ ] **Step 6: Run focused tests**

Run: `python -m pytest backend/tests/test_assessment_schema.py backend/tests/test_worker.py backend/tests/test_generator.py backend/tests/test_llm_client.py -q`

Expected: PASS. Update existing valid fixtures to include the newly required fields; do not weaken assertions.

- [ ] **Step 7: Run the backend suite**

Run: `python -m pytest backend/tests -q`

Expected: PASS, apart from already-documented non-failing pytest warnings.

- [ ] **Step 8: Leave changes uncommitted**

Report modified files and test results so the user can make the commit as sole author.
