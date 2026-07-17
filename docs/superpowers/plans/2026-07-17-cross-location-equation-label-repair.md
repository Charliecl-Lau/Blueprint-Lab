# Cross-Location Equation Label Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated and repaired assessments use distinct equation labels for question and solution content, while reporting every cross-location conflict in one validation error.

**Architecture:** Keep the existing strict `QuestionResponse` boundary and single provider repair call. Strengthen the shared generation instruction, repair instruction, and deterministic OpenAI template; then detect the complete set of shared labels before existing per-location validation so the repair call receives actionable feedback without backend output rewriting.

**Tech Stack:** Python 3.12, Pydantic 2.9, pytest 8.3, Celery 5.4, Gemini structured JSON, Railway Docker deployments

## Global Constraints

- A label with `location: "question"` may appear only in the question body or option bodies.
- A label with `location: "solution"` may appear only in `model_answer`.
- Repeated mathematical expressions across question and solution must use distinct labels and separate equation entries.
- Preserve the exact accepted provider response; do not normalize or rewrite it in the backend.
- Keep exactly one repair call and no repair loop.
- Do not change the database schema, API response shape, frontend, or DOCX renderer.
- Increment `ACTUAL_PROMPT_GENERATOR_VERSION` from `"8"` to `"9"` and `OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION` from `"1"` to `"2"`.
- Preserve unrelated working-tree changes and commit only files named by each task.
- Every commit must have an explanatory paragraph body and no attribution trailers.

---

### Task 1: Make the prompt contract location-specific

**Files:**
- Modify: `backend/tests/test_actual_prompt.py`
- Modify: `backend/services/actual_prompt.py`
- Modify: `docs/actual_prompt_template.md`

**Interfaces:**
- Consumes: `build_generation_system_prompt(actual_prompt: str) -> str`, `build_assessment_repair_system_prompt(actual_prompt: str) -> str`, and `render_openai_actual_prompt(...) -> str`.
- Produces: generation and repair prompts that require disjoint question/solution labels, plus prompt version constants `"9"` and `"2"`.

- [ ] **Step 1: Write failing prompt-contract and version tests**

Add these imports to the existing import list in `backend/tests/test_actual_prompt.py`:

```python
from backend.services.actual_prompt import (
    ActualPromptValidationError,
    build_assessment_repair_system_prompt,
    build_generation_system_prompt,
    build_condition_label,
    build_structure_input,
    render_openai_actual_prompt,
    validate_actual_prompt,
)
```

Add these tests after `test_generation_and_structure_prompts_require_flat_word_equation_entries`:

```python
def test_generation_and_repair_prompts_require_location_specific_labels():
    generation_prompt = build_generation_system_prompt(OPENAI_ACTUAL_PROMPT)
    repair_prompt = build_assessment_repair_system_prompt(OPENAI_ACTUAL_PROMPT)

    for prompt in (generation_prompt, repair_prompt):
        assert "A label MUST NOT appear in both question and solution content" in prompt
        assert "create two equation entries with distinct labels" in prompt
    assert "Audit every equation label in every question" in repair_prompt


def test_openai_template_and_versions_require_location_specific_labels():
    prompt = render_openai()

    assert "A label must not appear in both question and solution content" in prompt
    assert "two equation entries with distinct labels" in prompt
    assert actual_prompt.ACTUAL_PROMPT_GENERATOR_VERSION == "9"
    assert actual_prompt.OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION == "2"
```

- [ ] **Step 2: Run the tests and verify the expected failures**

Run:

```powershell
python -m pytest backend/tests/test_actual_prompt.py::test_generation_and_repair_prompts_require_location_specific_labels backend/tests/test_actual_prompt.py::test_openai_template_and_versions_require_location_specific_labels -q
```

Expected: both tests fail because the cross-location wording is absent and the versions remain `"8"` and `"1"`.

- [ ] **Step 3: Strengthen shared generation and repair instructions**

In `backend/services/actual_prompt.py`, update the constants to:

```python
ACTUAL_PROMPT_GENERATOR_VERSION = "9"
OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION = "2"
```

After the sentence that introduces `location` in `EQUATION_GENERATION_INSTRUCTION`, add:

```python
    "Set location to question when the label appears in body or an option body, and "
    "set location to solution when it appears in model_answer. A label MUST NOT "
    "appear in both question and solution content. If the same mathematical "
    "expression is needed in both, create two equation entries with distinct labels "
    "and matching locations, then use the corresponding label in each place. "
```

Extend `ASSESSMENT_REPAIR_INSTRUCTION` before its final data-safety sentence:

```python
    "Audit every equation label in every question, not only the first label named in "
    "the validation error. Split any label used in both question and solution content "
    "into two equation entries with distinct labels and matching locations, and update "
    "all corresponding references. "
```

- [ ] **Step 4: Reinforce the rule in the deterministic OpenAI template**

In `docs/actual_prompt_template.md`, immediately after the paragraph beginning `For every mathematical expression`, add:

```markdown
Set location to question when the label appears in the question body or an answer option, and set location to solution when it appears in the model answer. A label must not appear in both question and solution content. If the same mathematical expression is needed in both, create two equation entries with distinct labels and matching locations, then use the corresponding label in each place.
```

- [ ] **Step 5: Run the focused prompt tests**

Run:

```powershell
python -m pytest backend/tests/test_actual_prompt.py backend/tests/test_reproducibility.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit the prompt contract**

```powershell
git add -- backend/tests/test_actual_prompt.py backend/services/actual_prompt.py docs/actual_prompt_template.md
git commit -m "Require location-specific equation labels" -m "Clarify generation and repair prompts so a label belongs exclusively to question or solution content, with duplicate expressions represented by distinct entries. Increment prompt provenance versions so corrected runs are distinguishable from earlier ambiguous generations."
```

---

### Task 2: Report every cross-location label conflict

**Files:**
- Modify: `backend/tests/test_assessment_schema.py`
- Modify: `backend/tests/test_worker.py`
- Modify: `backend/schemas/assessment_schema.py`

**Interfaces:**
- Consumes: `_equation_references(text: Optional[str]) -> List[str]` and `QuestionResponse.validate_flat_equation_references()`.
- Produces: one `ValueError` with stable text `equation labels referenced from both question and solution: <sorted labels>` before the existing individual location checks, plus worker-level proof that the bounded repair succeeds with split labels.

- [ ] **Step 1: Write the run-19-shaped failing validator test**

Add this test after `test_flat_equation_references_accept_question_and_solution_locations`:

```python
def test_flat_equation_references_report_all_cross_location_labels(
    complete_payload,
):
    shared_labels = [
        "g_mix_def",
        "g_mix_res",
        "h_mix_val",
        "s_mix_def",
        "temp",
        "xa_val",
    ]
    question = complete_payload["questions"][0]
    question["body"] = "Use " + " ".join(
        f"[[EQ:{label}]]" for label in shared_labels
    )
    question["model_answer"] = "Apply " + " ".join(
        f"[[EQ:{label}]]" for label in reversed(shared_labels)
    )
    question["equations"] = [
        {
            "label": label,
            "expression": f"{label} = value",
            "location": "question",
        }
        for label in shared_labels
    ]

    with pytest.raises(ValidationError) as exc_info:
        AssessmentGenerationResponse.model_validate(complete_payload)

    assert (
        "equation labels referenced from both question and solution: "
        "g_mix_def, g_mix_res, h_mix_val, s_mix_def, temp, xa_val"
        in str(exc_info.value)
    )
```

- [ ] **Step 2: Write the failing worker regression test**

Add this test after `test_generation_pipeline_repairs_plain_formula_text_before_docx_creation` in `backend/tests/test_worker.py`:

```python
def test_generation_pipeline_repairs_cross_location_equation_labels(
    generation_fixture,
    test_db,
):
    rejected_question = complete_question(
        question_type="short_answer",
        body="Calculate [[EQ:g_mix_def]] at [[EQ:temp]].",
        model_answer=(
            "Apply [[EQ:g_mix_def]] at [[EQ:temp]] to obtain "
            "[[EQ:g_mix_result]]."
        ),
    )
    rejected_question["equations"] = [
        {
            "label": "g_mix_def",
            "expression": "G_mix = H_mix - T S_mix",
            "location": "question",
        },
        {
            "label": "temp",
            "expression": "T = 1000 K",
            "location": "question",
        },
        {
            "label": "g_mix_result",
            "expression": "G_mix = -5.76 kJ/mol",
            "location": "solution",
        },
    ]
    repaired_question = complete_question(
        question_type="short_answer",
        body="Calculate [[EQ:g_mix_question]] at [[EQ:temp_question]].",
        model_answer=(
            "Apply [[EQ:g_mix_solution]] at [[EQ:temp_solution]] to obtain "
            "[[EQ:g_mix_result]]."
        ),
    )
    repaired_question["equations"] = [
        {
            "label": "g_mix_question",
            "expression": "G_mix = H_mix - T S_mix",
            "location": "question",
        },
        {
            "label": "temp_question",
            "expression": "T = 1000 K",
            "location": "question",
        },
        {
            "label": "g_mix_solution",
            "expression": "G_mix = H_mix - T S_mix",
            "location": "solution",
        },
        {
            "label": "temp_solution",
            "expression": "T = 1000 K",
            "location": "solution",
        },
        {
            "label": "g_mix_result",
            "expression": "G_mix = -5.76 kJ/mol",
            "location": "solution",
        },
    ]
    rejected_raw = __import__("json").dumps({"questions": [rejected_question]})
    repaired_raw = __import__("json").dumps({"questions": [repaired_question]})
    llm = MagicMock()
    llm.generate.side_effect = [
        result(rejected_raw, 20, 8, 28),
        result(repaired_raw, 12, 6, 18),
    ]

    mock_redis = run_pipeline_synchronously(generation_fixture, test_db, llm)

    test_db.refresh(generation_fixture)
    assert generation_fixture.status == "complete", generation_fixture.error_message
    assert generation_fixture.assessment.raw_response_text == repaired_raw
    assert generation_fixture.document_artifact.content == b"PK-generation-docx"
    assert llm.generate.call_count == 2
    repair_call = llm.generate.call_args_list[1]
    assert (
        "equation labels referenced from both question and solution: "
        "g_mix_def, temp"
        in repair_call.kwargs["user_message"]
    )
    assert "Audit every equation label in every question" in (
        repair_call.kwargs["system_prompt"]
    )
    usage_stages = [
        usage.stage
        for usage in test_db.query(ModelCallUsage)
        .filter_by(run_id=generation_fixture.id)
        .order_by(ModelCallUsage.id)
        .all()
    ]
    assert usage_stages == ["assessment", "repair"]
    assert generation_fixture.model_call_count == 2
    assert generation_fixture.total_tokens == 46
    mock_redis.evaluation_delay.assert_called_once_with(generation_fixture.id)
```

- [ ] **Step 3: Run both new tests and verify the old first-label feedback fails them**

Run:

```powershell
python -m pytest backend/tests/test_assessment_schema.py::test_flat_equation_references_report_all_cross_location_labels backend/tests/test_worker.py::test_generation_pipeline_repairs_cross_location_equation_labels -q
```

Expected: both tests fail because the validator reports only `g_mix_def` using the old location-mismatch message, so the worker repair request does not contain the complete conflict set.

- [ ] **Step 4: Add complete shared-label detection before location checks**

In `QuestionResponse.validate_flat_equation_references`, immediately after unknown-label validation and before the two existing location loops, add:

```python
        shared_labels = sorted(
            set(question_references) & set(solution_references)
        )
        if shared_labels:
            raise ValueError(
                "equation labels referenced from both question and solution: "
                + ", ".join(shared_labels)
            )
```

Keep both existing location loops unchanged so a label referenced from only one side but carrying the wrong `location` still fails with its current focused error.

- [ ] **Step 5: Run the complete assessment-schema and worker suites**

Run:

```powershell
python -m pytest backend/tests/test_assessment_schema.py backend/tests/test_worker.py -q
```

Expected: all tests pass, including the existing single-side mismatch test, bounded invalid-repair test, and the new split-label repair test.

- [ ] **Step 6: Commit complete conflict reporting and worker coverage**

```powershell
git add -- backend/tests/test_assessment_schema.py backend/tests/test_worker.py backend/schemas/assessment_schema.py
git commit -m "Report all cross-location equation labels" -m "Detect the full intersection of question and solution equation references before individual location checks. Prove the bounded repair can split shared expressions into location-specific labels while preserving response provenance, usage accounting, and artifact creation."
```

---

### Task 3: Verify and deploy the fix

**Files:**
- Verify only: `Dockerfile`
- Verify only: `Dockerfile.worker`
- Verify only: all files changed by Tasks 1–2

**Interfaces:**
- Consumes: all prompt, validation, and worker changes from Tasks 1–2.
- Produces: passing local suites, buildable API and worker images, pushed commits, and successful Railway deployments.

- [ ] **Step 1: Run focused equation and rendering suites**

Run:

```powershell
python -m pytest backend/tests/test_actual_prompt.py backend/tests/test_reproducibility.py backend/tests/test_assessment_schema.py backend/tests/test_worker.py backend/tests/test_docx_exporter.py backend/tests/test_omml.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run the full non-integration backend suite**

Run:

```powershell
python -m pytest backend/tests -q --ignore=backend/tests/integration
```

Expected: all tests pass with zero failures.

- [ ] **Step 3: Check the final diff and working-tree isolation**

Run:

```powershell
git diff --check HEAD~2..HEAD
git status --short
```

Expected: no whitespace errors; unrelated pre-existing changes remain unstaged and unchanged.

- [ ] **Step 4: Build both deployment images**

Run:

```powershell
docker build -f Dockerfile.worker -t blueprint-lab-worker-equation-label-test .
docker build -f Dockerfile -t blueprint-lab-api-equation-label-test .
```

Expected: both builds exit successfully and copy `docs/actual_prompt_template.md`.

- [ ] **Step 5: Push the reviewed commits**

```powershell
git push origin main
```

Expected: `origin/main` advances through the design, plan, and two implementation commits without including unrelated working-tree files.

- [ ] **Step 6: Monitor Railway API and worker rollout**

Run `railway status --json` and inspect the `production` environment until `Blueprint-Lab` and `worker` both report `SUCCESS` for the pushed head commit.

Expected: both services reach `SUCCESS`; the previous instances remain available until replacement.

- [ ] **Step 7: Verify the public health endpoint**

Run:

```powershell
Invoke-WebRequest -UseBasicParsing https://blueprintlab.up.railway.app/health
```

Expected: HTTP `200` with body `ok`.

- [ ] **Step 8: Hand off a production generation retry**

Do not silently retry run 19 because doing so creates a new database run and incurs provider usage. Report the successful deployment and ask the user to retry the same end-to-end generation from the website, or obtain explicit approval before invoking the retry endpoint.
