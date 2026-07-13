# Assessment JSON Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent assessment parsing failures caused by generated prompts that omit the required top-level `questions` array.

**Architecture:** Keep the parser strict and enforce its contract one stage earlier. Provider structure instructions generate the contract, while `validate_actual_prompt` acts as the boundary check before the assessment model call.

**Tech Stack:** Python 3.9, Pydantic 2, pytest

## Global Constraints

- Preserve provider-specific Markdown and XML prompt structures.
- Require a JSON object with a top-level `questions` array.
- Do not normalize incompatible assessment responses in the parser.

---

### Task 1: Enforce the assessment JSON root contract

**Files:**
- Modify: `backend/tests/test_actual_prompt.py`
- Modify: `backend/services/structure_system_prompts.py`
- Modify: `backend/services/actual_prompt.py`

**Interfaces:**
- Consumes: `get_structure_system_prompt(prompt_structure)` and `validate_actual_prompt(prompt_structure, raw_text)`
- Produces: provider instructions and validation requiring the literal `questions` root field

- [ ] **Step 1: Write failing tests**

Add assertions that both structure system prompts require a top-level `questions` array,
that prompts omitting `questions` are rejected, and that contract-compliant prompts pass.

- [ ] **Step 2: Verify tests fail**

Run: `python -m pytest backend/tests/test_actual_prompt.py -q`

Expected: failures showing the instructions and validation do not enforce `questions`.

- [ ] **Step 3: Implement the minimal contract enforcement**

Update both structure system prompts to state the exact root shape. Add a shared validation
check that requires the literal `questions` JSON field before provider-specific checks.

- [ ] **Step 4: Verify focused and worker tests**

Run: `python -m pytest backend/tests/test_actual_prompt.py backend/tests/test_worker.py -q`

Expected: all tests pass.

- [ ] **Step 5: Retry through a new generation**

Create a new run through the existing API/UI rather than mutating the evidence captured by
failed run 3. Confirm the new run reaches `complete` and has a document artifact.
