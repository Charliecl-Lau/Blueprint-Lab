# Flat Provider Math Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Gemini's recursive assessment response schema with a flat equation-expression contract, normalize expressions into the existing internal math AST, and bound provider calls with a 60-second timeout.

**Architecture:** Dedicated provider Pydantic models describe only flat question text and linear equations. `generate_questions` validates provider output, deterministically enriches each equation with a `MathNode`, then validates the unchanged canonical assessment model. The shared Google Gen AI client receives a 60-second HTTP timeout so all generation stages fail and retry visibly instead of hanging.

**Tech Stack:** Python 3.9, Pydantic 2.9, google-genai 1.47, pytest 8.3, existing linear-math parser and Celery worker pipeline.

## Global Constraints

- Keep `AssessmentGenerationResponse`, `QuestionResponse`, and `MathNode` as the canonical application and storage contract.
- Do not change database models or add a migration.
- Do not change `concept_map_bridge` behavior or metadata.
- Provider equations require `label`, non-empty `expression`, and `location`; they do not expose `math`.
- Provider questions do not expose `body_segments`, `model_answer_segments`, or option `segments`.
- Store both the original linear expression and its deterministic internal AST.
- Preserve existing bounded Celery retries and failed-call token accounting.
- Configure the Google Gen AI client with a 60,000-millisecond HTTP timeout.
- Every commit message must contain a subject and an explanatory paragraph body, with no attribution trailer.

---

## File Structure

- Modify `backend/schemas/assessment_schema.py`: define the dedicated flat provider models and export their generated JSON Schema.
- Modify `backend/services/generator.py`: validate flat provider output, parse equation expressions, and return the canonical assessment model.
- Modify `backend/services/llm_client.py`: configure the shared provider HTTP timeout.
- Modify `backend/tests/test_assessment_schema.py`: prove the provider schema is flat and the canonical schema remains strict.
- Modify `backend/tests/test_generator.py`: prove provider output is normalized into math ASTs for all protected notation cases.
- Modify `backend/tests/test_llm_client.py`: prove the Google client receives the timeout.
- Modify `backend/tests/test_worker.py` only if existing worker assertions assume recursive schema fields.

### Task 1: Replace the Recursive Provider Schema

**Files:**
- Modify: `backend/schemas/assessment_schema.py`
- Modify: `backend/tests/test_assessment_schema.py`

**Interfaces:**
- Consumes: existing `QuestionMetadata`, `QualityCheckSchema`, and literal field values.
- Produces: `ProviderAssessmentGenerationResponse` and `ASSESSMENT_PROVIDER_SCHEMA: dict`.

- [ ] **Step 1: Replace the recursive compatibility tests with a failing flat-contract test**

Add provider-schema assertions equivalent to:

```python
def test_provider_schema_uses_flat_equations_without_recursive_math_defs():
    definitions = ASSESSMENT_PROVIDER_SCHEMA["$defs"]
    question = definitions["ProviderQuestionResponse"]
    equation = definitions["ProviderEquationSchema"]
    option = definitions["ProviderMCQOptionSchema"]

    assert {
        "MathNode",
        "EquationMathNode",
        "FractionMathNode",
        "SequenceMathNode",
    }.isdisjoint(definitions)
    assert "body_segments" not in question["properties"]
    assert "model_answer_segments" not in question["properties"]
    assert "segments" not in option["properties"]
    assert "math" not in equation["properties"]
    assert {"label", "expression", "location"} <= set(equation["required"])
    assert equation["properties"]["expression"]["minLength"] == 1
```

Keep the existing test that validates malformed canonical structured fractions so the provider change cannot weaken the application contract.

- [ ] **Step 2: Run the new test and verify the recursive schema makes it fail**

Run:

```powershell
python -m pytest backend/tests/test_assessment_schema.py::test_provider_schema_uses_flat_equations_without_recursive_math_defs -q
```

Expected: FAIL because recursive math definitions and structured segment fields are present.

- [ ] **Step 3: Add dedicated flat provider Pydantic models**

In `backend/schemas/assessment_schema.py`, add models after the canonical assessment response:

```python
class ProviderMCQOptionSchema(BaseModel):
    model_config = {"extra": "forbid"}

    body: str
    is_correct: bool


class ProviderEquationSchema(BaseModel):
    model_config = {"extra": "forbid"}

    label: str
    expression: str = Field(min_length=1)
    location: Literal["question", "solution"]


class ProviderQuestionResponse(BaseModel):
    model_config = {"protected_namespaces": (), "extra": "forbid"}

    type: Literal["mcq", "short_answer", "long_answer"]
    metadata: QuestionMetadata
    body: str
    options: List[ProviderMCQOptionSchema] = Field(default_factory=list)
    model_answer: Optional[str] = None
    equations: List[ProviderEquationSchema]
    quality_checks: List[QualityCheckSchema] = Field(default_factory=list)
    revision_options: List[str] = Field(min_length=2, max_length=3)


class ProviderAssessmentGenerationResponse(BaseModel):
    model_config = {"extra": "forbid"}

    questions: List[ProviderQuestionResponse]
```

Delete `_gemini_provider_schema` and its `deepcopy` import. Define:

```python
ASSESSMENT_PROVIDER_SCHEMA = (
    ProviderAssessmentGenerationResponse.model_json_schema()
)
```

- [ ] **Step 4: Run assessment-schema tests**

Run:

```powershell
python -m pytest backend/tests/test_assessment_schema.py -q
```

Expected: all assessment-schema tests pass after updating provider-only definition names in existing assertions.

- [ ] **Step 5: Commit the flat provider contract**

```powershell
git add backend/schemas/assessment_schema.py backend/tests/test_assessment_schema.py
git commit -m "Define a flat Gemini assessment contract" -m "Replace the recursive provider response schema with dedicated flat Pydantic models that require linear equation expressions. Preserve the canonical recursive math contract for application validation and storage while removing schema structures that cause Gemini requests to hang."
```

### Task 2: Normalize Linear Equations into Canonical Math ASTs

**Files:**
- Modify: `backend/services/generator.py`
- Modify: `backend/tests/test_generator.py`

**Interfaces:**
- Consumes: `ProviderAssessmentGenerationResponse.model_validate`, `_parse_json`, and `parse_linear_expression(expression: str) -> dict`.
- Produces: `generate_questions(raw_text: str) -> AssessmentGenerationResponse` with both `expression` and `math` populated.

- [ ] **Step 1: Replace the recursive-input generator test with failing normalization tests**

Create a small valid flat payload fixture whose body references each equation label. Add one parameterized test:

```python
@pytest.mark.parametrize(
    "expression,expected_type",
    [
        ("x_A", "subscript"),
        ("x_B", "subscript"),
        ("x_A^2", "superscript"),
        ("DeltaH/(T DeltaS)", "fraction"),
        ("sqrt(x_A)", "radical"),
        ("K^-1", "superscript"),
    ],
)
def test_generate_questions_normalizes_linear_equations(
    expression,
    expected_type,
):
    payload = complete_flat_payload(expression)
    result = generate_questions(json.dumps(payload))
    equation = result.questions[0].equations[0]

    assert equation.expression == expression
    assert equation.math.type == expected_type
```

For `x_A^2`, additionally assert `equation.math.base.type == "subscript"`.
For `K^-1`, assert the superscript is a sequence containing `-` and `1`.

- [ ] **Step 2: Run the generator tests and verify flat output fails before normalization**

Run:

```powershell
python -m pytest backend/tests/test_generator.py -q
```

Expected: FAIL because `generate_questions` currently validates directly against the canonical model and leaves `math` unset.

- [ ] **Step 3: Implement provider validation and deterministic normalization**

Update `backend/services/generator.py`:

```python
from backend.schemas.assessment_schema import (
    AssessmentGenerationResponse,
    ProviderAssessmentGenerationResponse,
)
from backend.services.omml import parse_linear_expression


def _canonical_payload(
    provider: ProviderAssessmentGenerationResponse,
) -> dict:
    payload = provider.model_dump()
    for question in payload["questions"]:
        for equation in question["equations"]:
            equation["math"] = parse_linear_expression(
                equation["expression"]
            )
    return payload


def generate_questions(raw_text: str) -> AssessmentGenerationResponse:
    provider = ProviderAssessmentGenerationResponse.model_validate(
        _parse_json(raw_text)
    )
    return AssessmentGenerationResponse.model_validate(
        _canonical_payload(provider)
    )
```

Keep normalization private to the generator service so schema models remain declarative.

- [ ] **Step 4: Verify generator and worker parsing behavior**

Run:

```powershell
python -m pytest backend/tests/test_generator.py backend/tests/test_worker.py -q
```

Expected: PASS after updating worker fixtures that still return `math` or structured segments to return the flat provider format.

- [ ] **Step 5: Commit deterministic math normalization**

```powershell
git add backend/services/generator.py backend/tests/test_generator.py backend/tests/test_worker.py
git commit -m "Normalize provider equations into math ASTs" -m "Validate Gemini output through the flat provider contract, preserve each original linear expression, and deterministically populate the canonical MathNode representation before persistence. Cover subscripts, combined scripts, fractions, radicals, and signed superscripts."
```

### Task 3: Bound Provider Calls

**Files:**
- Modify: `backend/services/llm_client.py`
- Modify: `backend/tests/test_llm_client.py`

**Interfaces:**
- Consumes: `google.genai.types.HttpOptions`.
- Produces: every `LLMClient` instance uses a 60,000-millisecond provider timeout.

- [ ] **Step 1: Add a failing timeout-construction test**

Add:

```python
def test_llm_client_configures_sixty_second_provider_timeout():
    with patch("backend.services.llm_client.genai.Client") as mock_client:
        LLMClient()

    kwargs = mock_client.call_args.kwargs
    assert kwargs["api_key"] == settings.google_api_key
    assert kwargs["http_options"].timeout == 60_000
```

- [ ] **Step 2: Run the timeout test and verify it fails**

Run:

```powershell
python -m pytest backend/tests/test_llm_client.py::test_llm_client_configures_sixty_second_provider_timeout -q
```

Expected: FAIL because `http_options` is not currently supplied.

- [ ] **Step 3: Configure the Google client timeout**

In `LLMClient.__init__`, replace client construction with:

```python
self._client = genai.Client(
    api_key=settings.google_api_key,
    http_options=types.HttpOptions(timeout=60_000),
)
```

Do not add a second application-level retry; the worker already owns bounded retries and stage-specific failure persistence.

- [ ] **Step 4: Run the LLM client and provider-failure worker tests**

Run:

```powershell
python -m pytest backend/tests/test_llm_client.py backend/tests/test_worker.py::test_failed_provider_call_is_recorded_without_tokens backend/tests/test_worker.py::test_openai_generation_provider_failure_is_stage_specific -q
```

Expected: PASS, proving timeout configuration does not change failure accounting.

- [ ] **Step 5: Commit provider timeout handling**

```powershell
git add backend/services/llm_client.py backend/tests/test_llm_client.py
git commit -m "Bound Gemini provider requests" -m "Configure the shared Google Gen AI client with a sixty-second HTTP timeout so stalled prompt, assessment, repair, and evaluation requests enter the existing stage-specific retry and error workflow instead of blocking indefinitely."
```

### Task 4: Full Contract Verification

**Files:**
- Verify: `backend/schemas/assessment_schema.py`
- Verify: `backend/services/generator.py`
- Verify: `backend/services/llm_client.py`
- Verify: `frontend/src/math/linearMath.ts`
- Verify: `backend/services/omml.py`

**Interfaces:**
- Consumes: the completed flat provider contract, canonical normalization, and timeout configuration.
- Produces: evidence that all backend and frontend workflows remain compatible.

- [ ] **Step 1: Prove the provider schema contains no recursive references**

Run:

```powershell
@'
from backend.schemas.assessment_schema import ASSESSMENT_PROVIDER_SCHEMA

rendered = repr(ASSESSMENT_PROVIDER_SCHEMA)
assert "MathNode" not in rendered
assert "$ref" not in rendered or all(
    name not in rendered
    for name in (
        "EquationMathNode",
        "FractionMathNode",
        "SequenceMathNode",
    )
)
print("flat provider schema verified")
'@ | python -
```

Expected: `flat provider schema verified`.

- [ ] **Step 2: Run the complete backend suite**

Run:

```powershell
python -m pytest backend/tests -q
```

Expected: all backend tests pass, with only the repository's documented skips and existing pytest-asyncio warning.

- [ ] **Step 3: Run frontend unit tests**

Run:

```powershell
npm test -- --run
```

Working directory: `frontend`

Expected: all frontend tests pass, including `linearMath.test.ts`.

- [ ] **Step 4: Build the frontend**

Run:

```powershell
npm run build
```

Working directory: `frontend`

Expected: exit code 0.

- [ ] **Step 5: Inspect the final diff and repository status**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors and no unintended tracked files. Existing untracked `.codex-runtime/` and `prompt/anthropic-skills/` remain untouched.

- [ ] **Step 6: Report deployment readiness**

Report the commits, backend test count, frontend test count, build result, and the fact that a live Gemini smoke test is intentionally not run without separate approval because it consumes provider quota.
