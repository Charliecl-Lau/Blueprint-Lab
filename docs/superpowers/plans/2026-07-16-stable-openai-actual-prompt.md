# Stable OpenAI Actual Prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render every OpenAI Actual Prompt deterministically from the canonical template while leaving Anthropic prompt compilation provider-driven.

**Architecture:** `backend.services.actual_prompt` will own loading, mapping, rendering, and validation for the canonical OpenAI template. The worker will select the local renderer for OpenAI and the existing provider compiler for Anthropic, then converge on the existing persistence, hashing, and assessment-generation flow.

**Tech Stack:** Python 3, pathlib, Pydantic models, SQLAlchemy, Celery, pytest, and unittest.mock.

## Global Constraints

- Apply deterministic rendering only when `prompt_structure == "openai"`.
- Use `docs/actual_prompt_template.md` as the canonical stable wording.
- Replace only approved named placeholders; preserve literal JSON braces.
- Insert complete enabled factor content in this order: Concept Bridge, Few-shot Examples, Reference Content, Reasoning Guidance.
- Omit disabled factors and use `None Selected` when all factors are disabled.
- Map an MSE202 topic only to `mse202_concepts` and an MSE302 topic only to `mse302_concepts`; use `Not Provided` for the opposite and unknown-course fields.
- Insert Concept Bridge content when enabled and `Not Provided` when disabled.
- Tell the assessment model to derive Materials Science Context from course, topic, and learning objective.
- Include trimmed Additional Instruction only when supplied.
- Preserve Anthropic prompt construction and XML validation.
- Preserve unrelated working-tree changes, especially the existing edit in `backend/services/structure_system_prompts.py`.
- Never add attribution trailers. Every commit must contain an explanatory paragraph body.

## File Responsibilities

- `docs/actual_prompt_template.md`: canonical OpenAI prompt and named insertion markers.
- `backend/services/actual_prompt.py`: template constants, renderer, value mapping, factor formatting, and validation.
- `backend/services/prompt_generator.py`: compatibility wrapper for serialized prompt input.
- `backend/workers/assessment_worker.py`: provider-specific prompt construction and common persistence/generation flow.
- `backend/tests/test_actual_prompt.py`: renderer and validation unit coverage.
- `backend/tests/test_prompt_generator.py`: serialized estimated-time coverage.
- `backend/tests/test_worker.py`: call counts, provenance, retries, usage, and Anthropic regression coverage.
- `backend/tests/test_reproducibility.py`: deterministic prompt-hash regression.

---

### Task 1: Build the deterministic OpenAI renderer

**Files:**
- Modify: `docs/actual_prompt_template.md`
- Modify: `backend/services/actual_prompt.py`
- Modify: `backend/tests/test_actual_prompt.py`

**Interfaces:**
- Consumes: scalar experiment fields, `PromptFactors`, and `dict[str, str]` factor inputs.
- Produces: `OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION: str`, `OPENAI_TEMPLATE_PROVENANCE: str`, and `render_openai_actual_prompt(*, course: str, topic: str, learning_objectives: str, assessment_type: str, difficulty: str, number_of_questions: int, estimated_time_minutes: int, cognitive_demand: str, additional_instruction: Optional[str], factors: PromptFactors, factor_inputs: dict[str, str]) -> str`.

- [ ] **Step 1: Add failing stability and mapping tests**

Add the renderer import and this helper to `backend/tests/test_actual_prompt.py`:

```python
def render_openai(**overrides):
    values = {
        "course": "MSE202",
        "topic": "Gibbs Phase Rule",
        "learning_objectives": "Apply the phase rule to alloy systems.",
        "assessment_type": "short_answer",
        "difficulty": "medium",
        "number_of_questions": 2,
        "estimated_time_minutes": 30,
        "cognitive_demand": "apply_analyze",
        "additional_instruction": None,
        "factors": PromptFactors(),
        "factor_inputs": {},
    }
    values.update(overrides)
    return render_openai_actual_prompt(**values)
```

Add exact tests for stability and literal JSON brace preservation:

```python
def test_openai_template_rendering_is_stable_and_preserves_json():
    first = render_openai()
    second = render_openai()
    assert first == second
    assert first.startswith("Role\n")
    assert '"questions": [' in first
    assert "{learning_objective}" not in first
    assert "Course:\nMSE202" in first
    assert "Cognitive Demand:\nApply/Analyze" in first
    assert "Estimated Time:\n30 minutes" in first
    assert '"type": "short_answer"' in first


def test_openai_template_changes_only_substituted_values():
    baseline = render_openai(topic="Gibbs Phase Rule")
    changed = render_openai(topic="Chemical Potential")
    assert baseline != changed
    assert baseline.replace("Gibbs Phase Rule", "Chemical Potential") == changed
```

Add the course mapping parameterization:

```python
@pytest.mark.parametrize(
    ("course", "mse202", "mse302"),
    [
        (" mse202 ", "Gibbs Phase Rule", "Not Provided"),
        ("MSE302", "Not Provided", "Gibbs Phase Rule"),
        ("ENGR 101", "Not Provided", "Not Provided"),
    ],
)
def test_openai_template_maps_topic_to_course_concept(course, mse202, mse302):
    prompt = render_openai(course=course)
    assert f"MSE202 Concept(s):\n{mse202}" in prompt
    assert f"MSE302 Concept(s):\n{mse302}" in prompt
```

- [ ] **Step 2: Add failing factor, context, and Additional Instruction tests**

```python
def test_openai_template_formats_enabled_factors_in_stable_order():
    prompt = render_openai(
        factors=PromptFactors(
            concept_bridge=True, few_shot=True,
            reference_content=True, reasoning_guidance=True,
        ),
        factor_inputs={
            "concept_bridge": "Connect chemical potential to phase stability.",
            "few_shot": "Example question and answer.",
            "reference_content": "Supplied phase-diagram excerpt.",
            "reasoning_guidance": "Check phase-count assumptions.",
        },
    )
    blocks = [
        "Concept Bridge:\nConnect chemical potential to phase stability.",
        "Few-shot Examples:\nExample question and answer.",
        "Reference Content:\nSupplied phase-diagram excerpt.",
        "Reasoning Guidance:\nCheck phase-count assumptions.",
    ]
    positions = [prompt.index(block) for block in blocks]
    assert positions == sorted(positions)
    assert "Concept Map Bridge:\nConnect chemical potential to phase stability." in prompt


def test_openai_template_handles_disabled_factors_and_optional_instruction():
    prompt = render_openai(factor_inputs={"few_shot": "must not appear"})
    instructed = render_openai(
        additional_instruction="  Use one laboratory scenario.  "
    )
    assert "Selected Prompt Design Factors:\nNone Selected" in prompt
    assert "Concept Map Bridge:\nNot Provided" in prompt
    assert "must not appear" not in prompt
    assert "Additional Instruction:" not in prompt
    assert "Additional Instruction:\nUse one laboratory scenario." in instructed


def test_openai_template_delegates_materials_context_derivation():
    assert (
        "Materials Science Context:\n"
        "Derive from the supplied course, topic, and learning objective."
    ) in render_openai()


def test_openai_template_load_failure_is_classified(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.services.actual_prompt._OPENAI_TEMPLATE_PATH",
        tmp_path / "missing-template.md",
    )
    with pytest.raises(ActualPromptValidationError, match="cannot be loaded"):
        render_openai()
```

- [ ] **Step 3: Run the tests and verify the missing renderer failure**

Run: `python -m pytest backend/tests/test_actual_prompt.py -q`

Expected: collection fails because `render_openai_actual_prompt` is not defined.

- [ ] **Step 4: Add the conditional template marker**

In `docs/actual_prompt_template.md`, add `{additional_instruction_block}` immediately after the `{estimated_time}` line. Preserve all other stable prose and all literal JSON braces.

- [ ] **Step 5: Implement template constants and factor formatting**

In `backend/services/actual_prompt.py`, import `Path` and add:

```python
OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION = "1"
OPENAI_TEMPLATE_PROVENANCE = "local-template:docs/actual_prompt_template.md"
_OPENAI_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "actual_prompt_template.md"
)
_OPENAI_PLACEHOLDERS = (
    "learning_objective", "course", "topic", "question_type", "difficulty",
    "cognitive_demand", "number_of_questions", "estimated_time",
    "mse202_concepts", "mse302_concepts", "concept_bridge",
    "materials_science_context", "prompt_design_factors",
    "additional_instruction_block",
)


def _format_prompt_design_factors(
    factors: PromptFactors, factor_inputs: dict[str, str]
) -> str:
    blocks = []
    for name, label in _FACTOR_DEFINITIONS:
        if getattr(factors, name):
            blocks.append(f"{label}:\n{factor_inputs[name].strip()}")
    return "\n\n".join(blocks) if blocks else "None Selected"
```

- [ ] **Step 6: Implement minimal deterministic rendering**

Add `render_openai_actual_prompt` with the exact signature in this task's Interfaces block. Load `_OPENAI_TEMPLATE_PATH` with UTF-8 inside `try/except OSError`; translate an `OSError` into `ActualPromptValidationError("OpenAI Actual Prompt template cannot be loaded")`. Casefold the trimmed course and construct this values mapping:

```python
values = {
    "learning_objective": learning_objectives.strip(),
    "course": course.strip(),
    "topic": topic.strip(),
    "question_type": assessment_type,
    "difficulty": difficulty.strip(),
    "cognitive_demand": _COGNITIVE_DEMAND_LABELS.get(cognitive_demand, cognitive_demand),
    "number_of_questions": str(number_of_questions),
    "estimated_time": f"{estimated_time_minutes} minutes",
    "mse202_concepts": topic.strip() if normalized_course == "mse202" else "Not Provided",
    "mse302_concepts": topic.strip() if normalized_course == "mse302" else "Not Provided",
    "concept_bridge": (
        factor_inputs["concept_bridge"].strip()
        if factors.concept_bridge else "Not Provided"
    ),
    "materials_science_context": (
        "Derive from the supplied course, topic, and learning objective."
    ),
    "prompt_design_factors": _format_prompt_design_factors(factors, factor_inputs),
    "additional_instruction_block": (
        "Additional Instruction:\n" + additional_instruction.strip()
        if additional_instruction and additional_instruction.strip() else ""
    ),
}
```

Replace each token with `rendered.replace("{" + name + "}", values[name])`. Check every approved token after replacement, raise `ActualPromptValidationError` listing unresolved names, strip the final prompt, call `validate_actual_prompt("openai", rendered)`, and return it. Do not use `str.format`, because the canonical JSON braces are literal content.

- [ ] **Step 7: Align OpenAI validation with the canonical sections**

Set `_OPENAI_SECTIONS` to `Role`, `Personality`, `Goal (Dynamic)`, `Prompt Parameters (Dynamic)`, `Concept Mapping`, `Prompt Design Factors`, `Constraints`, `Output Format`, and `Stop Rules`. In `_validate_openai`, collect lines exactly equal to those headings, require the exact order and one occurrence each, require `raw_text.startswith("Role\n")`, and reject any remaining approved placeholder token. Keep the common code-fence and top-level `"questions"` checks and all Anthropic validation unchanged.

Update the unit-test `OPENAI_ACTUAL_PROMPT` fixture to contain the nine canonical headings. Add invalid cases for a duplicate `Concept Mapping` heading and an unresolved `{topic}` token.

- [ ] **Step 8: Verify and commit Task 1**

Run: `python -m pytest backend/tests/test_actual_prompt.py -q`

Expected: all tests pass.

Commit:

```powershell
git add docs/actual_prompt_template.md backend/services/actual_prompt.py backend/tests/test_actual_prompt.py
git commit -m "Render stable OpenAI Actual Prompts" -m "This adds deterministic rendering for the canonical OpenAI prompt, including explicit dynamic mappings, enabled factor content, and canonical-section validation. It eliminates prompt wording variation while preserving literal JSON syntax and rejecting unresolved values."
```

---

### Task 2: Carry estimated time through serialized inputs

**Files:**
- Modify: `backend/services/actual_prompt.py`
- Modify: `backend/services/prompt_generator.py`
- Modify: `backend/tests/test_actual_prompt.py`
- Modify: `backend/tests/test_prompt_generator.py`

**Interfaces:**
- Produces: `build_structure_input(..., estimated_time_minutes: int, ...) -> str` and `generate_prompt(..., estimated_time_minutes: int = 30, ...) -> str`.

- [ ] **Step 1: Write failing estimated-time tests**

Pass `estimated_time_minutes=45` to direct `build_structure_input` calls and assert `"Estimated Time: 45 minutes" in text`. Pass `estimated_time_minutes=50` to `generate_prompt` and assert `"Estimated Time: 50 minutes" in result`.

- [ ] **Step 2: Verify the signature failure**

Run: `python -m pytest backend/tests/test_actual_prompt.py backend/tests/test_prompt_generator.py -q`

Expected: failures report that the two functions do not accept `estimated_time_minutes`.

- [ ] **Step 3: Implement estimated-time propagation**

Add required `estimated_time_minutes: int` after `number_of_questions` in `build_structure_input` and append `f"Estimated Time: {estimated_time_minutes} minutes"` with the assessment details. Add `estimated_time_minutes: int = 30` to `generate_prompt` and forward it by name.

- [ ] **Step 4: Verify and commit Task 2**

Run: `python -m pytest backend/tests/test_actual_prompt.py backend/tests/test_prompt_generator.py -q`

Expected: all tests pass.

Commit:

```powershell
git add backend/services/actual_prompt.py backend/services/prompt_generator.py backend/tests/test_actual_prompt.py backend/tests/test_prompt_generator.py
git commit -m "Include estimated time in prompt inputs" -m "This carries estimated completion time through serialized prompt inputs and the compatibility wrapper. OpenAI rendering, Anthropic compilation, and reproducibility records now receive the same explicit value."
```

---

### Task 3: Route OpenAI workers through the local renderer

**Files:**
- Modify: `backend/services/actual_prompt.py`
- Modify: `backend/workers/assessment_worker.py`
- Modify: `backend/tests/test_worker.py`

**Interfaces:**
- Consumes: renderer and constants from Task 1 and estimated-time input from Task 2.
- Produces: persisted OpenAI prompts with local provenance and no `actual_prompt` usage row; unchanged provider provenance for Anthropic.

- [ ] **Step 1: Rewrite the main OpenAI worker expectation before implementation**

Use `render_openai_actual_prompt` to calculate `expected_prompt`, configure only the assessment `LLMResult`, and assert one `llm.generate` call with `build_generation_system_prompt(expected_prompt)`. Assert:

```python
assert generation_fixture.prompt.actual_prompt == expected_prompt
assert generation_fixture.prompt.structure_system_prompt == OPENAI_TEMPLATE_PROVENANCE
assert generation_fixture.prompt.structure_prompt_version == OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION
assert generation_fixture.prompt.structure_request_id is None
assert generation_fixture.prompt.structure_model == "local-template-renderer"
assert generation_fixture.prompt.structure_model_version == OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION
assert generation_fixture.prompt.structure_finish_reason == "LOCAL"
assert generation_fixture.prompt.structure_duration_ms is not None
```

Pass `estimated_time_minutes` into every test call to `build_structure_input`.

- [ ] **Step 2: Add an Anthropic regression test before implementation**

Create a condition/run with `prompt_structure="anthropic"`. Return the module's valid `ANTHROPIC_ACTUAL_PROMPT` fixture and then valid assessment JSON. Assert two provider calls, the first call uses `get_structure_system_prompt("anthropic")`, persisted request/model provenance comes from that result, and usage stages equal `["actual_prompt", "assessment"]`.

- [ ] **Step 3: Update retry and usage expectations before implementation**

For OpenAI tests, remove the generated prompt result from every side effect, expect only assessment usage rows, and subtract the old prompt-stage tokens from totals. Cover `actual_prompt_provider_error` only with an Anthropic run. Replace the malformed provider-prompt OpenAI test by patching `render_openai_actual_prompt` to raise `ActualPromptValidationError("template invalid")`; assert `actual_prompt_validation_error`, no persisted Prompt, and no provider call.

- [ ] **Step 4: Confirm failures against the old two-call flow**

Run: `python -m pytest backend/tests/test_worker.py -q`

Expected: OpenAI call-count/provenance/usage tests fail while the old worker still compiles prompts through the provider.

- [ ] **Step 5: Implement the OpenAI/Anthropic branch**

Always build `structure_input`, including `estimated_time_minutes=experiment.estimated_time_minutes`. For OpenAI, call `render_openai_actual_prompt` with experiment values, `_factors_from_condition(condition)`, and the complete `condition.factor_inputs`. Set:

```python
structure_system_prompt = OPENAI_TEMPLATE_PROVENANCE
structure_prompt_version = OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION
structure_request_id = None
structure_model = "local-template-renderer"
structure_model_version = OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION
structure_finish_reason = "LOCAL"
```

Catch `ActualPromptValidationError`, record `actual_prompt_validation_error`, publish error progress, and return before persistence or provider use. For Anthropic, retain `_call_gemini(stage="actual_prompt", ...)`, `actual_prompt_provider_error`, and provider provenance. Measure `structure_duration_ms` around either construction path. Converge on one `Prompt(...)` creation using the selected `actual_prompt` and provenance variables.

Increment `ACTUAL_PROMPT_GENERATOR_VERSION` from `"7"` to `"8"`. Retain the common validation after persistence so retry/resume still validates stored prompts.

- [ ] **Step 6: Verify and commit Task 3**

Run: `python -m pytest backend/tests/test_actual_prompt.py backend/tests/test_prompt_generator.py backend/tests/test_worker.py -q`

Expected: all tests pass.

Commit:

```powershell
git add backend/services/actual_prompt.py backend/workers/assessment_worker.py backend/tests/test_worker.py
git commit -m "Use local prompts for OpenAI runs" -m "This routes OpenAI conditions through the deterministic renderer and records explicit local provenance without creating a prompt-stage provider call. Anthropic retains provider compilation while both paths share persistence, hashing, validation, and assessment generation."
```

---

### Task 4: Verify reproducibility and regressions

**Files:**
- Modify: `backend/tests/test_reproducibility.py`
- Modify only if assertions require the new contract: `backend/tests/test_end_to_end_run_lifecycle.py`
- Modify only if assertions require the new contract: `backend/tests/test_api_runs.py`

**Interfaces:**
- Consumes: stable renderer and persisted worker behavior.
- Produces: evidence for deterministic hashes and unchanged downstream APIs.

- [ ] **Step 1: Add a deterministic hash regression**

Render one MSE302 prompt twice with identical explicit inputs. Build two hashes with `build_actual_prompt_hash`, `OPENAI_TEMPLATE_PROVENANCE`, `OPENAI_ACTUAL_PROMPT_TEMPLATE_VERSION`, `ACTUAL_PROMPT_GENERATOR_VERSION`, identical structure input, and identical model settings. Assert both rendered prompts and both hashes are equal.

- [ ] **Step 2: Run the focused lifecycle surface**

Run:

```powershell
python -m pytest backend/tests/test_actual_prompt.py backend/tests/test_prompt_generator.py backend/tests/test_worker.py backend/tests/test_reproducibility.py backend/tests/test_end_to_end_run_lifecycle.py backend/tests/test_api_runs.py -q
```

Expected: all tests pass. If a fixture directly calls `build_structure_input`, add its exact estimated-time value. If a fixture assumes two OpenAI calls or an OpenAI `actual_prompt` usage row, update only that assertion to the Task 3 contract.

- [ ] **Step 3: Run the full backend suite**

Run: `python -m pytest backend/tests -q`

Expected: all backend tests pass with no failures or errors.

- [ ] **Step 4: Inspect formatting and scope**

Run `git diff --check`, `git status --short`, and a scoped `git diff` over the files listed in this plan. Expect no whitespace errors, no accidental staging of pre-existing user changes, and no Anthropic behavior changes beyond required signature compatibility.

- [ ] **Step 5: Commit regression-only adjustments if present**

```powershell
git add backend/tests/test_reproducibility.py backend/tests/test_end_to_end_run_lifecycle.py backend/tests/test_api_runs.py
git commit -m "Verify stable prompt reproducibility" -m "This adds deterministic OpenAI prompt-hash coverage and aligns lifecycle expectations with local prompt rendering. The regression tests preserve API compatibility and confirm unchanged Anthropic and downstream assessment behavior."
```

Do not create an empty commit if Task 4 changes only `backend/tests/test_reproducibility.py`; include that file in this commit. Record exact passing test counts and the clean `git diff --check` result for the completion report.
