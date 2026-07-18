# Bounded Assessment Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permit a second targeted assessment-repair call when Gemini's first repair still fails strict equation-reference validation.

**Architecture:** Keep validation and error classification unchanged, but replace the single repair branch in the Celery worker with a bounded validate/repair loop. Persist every latest repair response before validating it, and reuse the existing `repair` usage stage so token and attempt accounting continue without schema changes.

**Tech Stack:** Python 3.9, Celery, Pydantic 2.9, SQLAlchemy, pytest, unittest.mock.

## Global Constraints

- Keep equation-reference validation strict.
- Allow at most two repair calls after the initial generation call.
- Each repair consumes the latest rejected JSON and latest validation error.
- Preserve existing provider-error and unavailable-reference-PDF classifications.
- Reuse the existing `repair` usage stage and database schema.
- Every commit message must include an explanatory paragraph body and no attribution trailers.

---

### Task 1: Cover repeated validation failures

**Files:**
- Modify: `backend/tests/test_worker.py:606`

**Interfaces:**
- Consumes: `run_pipeline_synchronously(...)`, `complete_question(...)`, `result(...)`, and `ModelCallUsage`.
- Produces: regression coverage requiring two repair calls and terminal failure only after both repairs are invalid.

- [ ] **Step 1: Add a failing second-repair success test**

Add `test_generation_pipeline_repairs_a_second_validation_failure`. Build three responses with the existing test helpers:

```python
initial_question = complete_question(
    question_type="short_answer",
    body="The gas constant is R = 8.314 J/(mol K).",
    model_answer="Use the supplied value.",
)
initial_question["equations"] = []
first_repair_question = complete_question(
    question_type="short_answer",
    body="Use alpha = (1/V)(partial V/partial T)_P to explain the result.",
    model_answer="Use the supplied relation.",
)
first_repair_question["equations"] = []
valid_question = complete_question(
    question_type="short_answer",
    body="Use [[EQ:thermal_expansion]] to explain the result.",
    model_answer="Use the supplied relation.",
)
valid_question["equations"] = [{
    "label": "thermal_expansion",
    "expression": "alpha = (1/V)(partial V/partial T)_P",
    "location": "question",
}]
```

Serialize each question with `json.dumps`, configure `llm.generate.side_effect` with assessment usage `(20, 8, 28)`, first-repair usage `(12, 6, 18)`, and second-repair usage `(10, 6, 16)`, then run the pipeline. Assert:

```python
assert generation_fixture.status == "complete", generation_fixture.error_message
assert generation_fixture.assessment.raw_response_text == valid_raw
assert llm.generate.call_count == 3
assert first_repair_raw in llm.generate.call_args_list[2].kwargs["user_message"]
assert usage_stages == ["assessment", "repair", "repair"]
assert generation_fixture.model_call_count == 3
assert generation_fixture.total_tokens == 62
mock_redis.evaluation_delay.assert_called_once_with(generation_fixture.id)
```

- [ ] **Step 2: Update the terminal boundary test**

Rename `test_generation_pipeline_stops_after_one_invalid_repair` to `test_generation_pipeline_stops_after_two_invalid_repairs`. Supply three invalid results and assert:

```python
assert llm.generate.call_count == 3
assert usage_stages == ["assessment", "repair", "repair"]
assert generation_fixture.model_call_count == 3
assert generation_fixture.total_tokens == 65
```

- [ ] **Step 3: Verify RED**

Run:

```powershell
python -m pytest backend/tests/test_worker.py::test_generation_pipeline_repairs_a_second_validation_failure backend/tests/test_worker.py::test_generation_pipeline_stops_after_two_invalid_repairs -v
```

Expected: both tests fail because the worker stops after one repair and records only two calls.

---

### Task 2: Implement bounded repair attempts

**Files:**
- Modify: `backend/workers/assessment_worker.py:42`
- Modify: `backend/workers/assessment_worker.py:438-499`
- Test: `backend/tests/test_worker.py`

**Interfaces:**
- Consumes: `generate_questions(raw_text)`, `_call_gemini(...)`, and the existing repair prompt builders.
- Produces: `_MAX_ASSESSMENT_REPAIR_ATTEMPTS: int` and a bounded loop assigning a validated `AssessmentGenerationResponse` to `generated`.

- [ ] **Step 1: Define the limit**

Add beside the existing module constants:

```python
_MAX_ASSESSMENT_REPAIR_ATTEMPTS = 2
```

- [ ] **Step 2: Replace the single repair branch**

Use this loop inside the existing outer parse/document error handler:

```python
generated = None
for repair_attempt in range(_MAX_ASSESSMENT_REPAIR_ATTEMPTS + 1):
    try:
        generated = generate_questions(result.raw_text)
        break
    except ValidationError as exc:
        if repair_attempt == _MAX_ASSESSMENT_REPAIR_ATTEMPTS:
            raise
        validation_error = str(exc)

    run.progress_message = "Repairing Assessment"
    db.commit()
    _publish_progress(experiment.id, run.id, condition.id, "generating")
    try:
        result = _call_gemini(
            self,
            db,
            run,
            llm,
            stage="repair",
            system_prompt=build_assessment_repair_system_prompt(
                prompt.actual_prompt
            ),
            user_message=build_assessment_repair_user_message(
                result.raw_text,
                validation_error,
            ),
            model_settings=run.model_settings,
            response_schema=ASSESSMENT_PROVIDER_SCHEMA,
            attachments=attachments,
        )
    except Exception as exc:
        if attachments and _is_reference_pdf_unavailable(exc):
            exc = RuntimeError(
                "An attached reference PDF is unavailable. Upload fresh PDFs and retry."
            )
            error_type = "reference_pdf_unavailable"
        else:
            error_type = "assessment_repair_provider_error"
        _record_error(db, run, error_type, exc)
        _publish_progress(experiment.id, run.id, condition.id, "error")
        return

    assessment.raw_response_text = result.raw_text
    assessment.output_hash = sha256_text(result.raw_text)
    run.request_id = result.provider_request_id
    run.model = result.model_name
    run.version = result.model_version
    run.finish_reason = result.finish_reason
    run.duration_ms = int((time.perf_counter() - generation_started) * 1000)
    db.commit()

assert generated is not None
```

- [ ] **Step 3: Verify GREEN with focused tests**

Run:

```powershell
python -m pytest backend/tests/test_worker.py::test_generation_pipeline_repairs_a_second_validation_failure backend/tests/test_worker.py::test_generation_pipeline_stops_after_two_invalid_repairs backend/tests/test_worker.py::test_generation_pipeline_repairs_plain_formula_text_before_docx_creation backend/tests/test_worker.py::test_generation_pipeline_repairs_cross_location_equation_labels -v
```

Expected: four tests pass.

- [ ] **Step 4: Run worker and backend regression suites**

Run:

```powershell
python -m pytest backend/tests/test_worker.py -v
python -m pytest backend/tests -q
```

Expected: both commands exit 0 with no failures.

- [ ] **Step 5: Review and commit**

Run `git diff --check` and inspect the worker/test diff. Stage only the worker, worker tests, and this plan. Commit with:

```text
Retry invalid assessment repairs

Allow one additional targeted repair when generated assessment JSON still
violates strict equation-reference validation. Preserve the latest response
and usage metadata on every attempt while retaining existing terminal error
behavior after the bounded retry limit.
```
