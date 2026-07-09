# Assessment Generator — Backend Plan 2: LLM Pipeline Services

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the six pure-Python service modules that form the 3-call LLM pipeline: framework templates, LLM client wrapper, Call 1 (Prompt Generator), Call 2 (Planner), Plan Gate Validator, and Call 3 (Generator).

**Architecture:** Each service is a standalone module with no FastAPI or Celery dependencies — they accept plain Python objects and return typed results. This makes them fully unit-testable with mocked LLMs. All six modules are consumed by the Celery worker defined in Plan 3.

**Tech Stack:** Python 3.11+, `google-genai`, Pydantic 2.x, pytest

**Prerequisites:** Plan 1 must be complete. All imports from `backend.models`, `backend.schemas`, and `backend.database` must resolve.

---

## File Map

| File | Responsibility |
|---|---|
| `backend/services/__init__.py` | Empty package marker |
| `backend/services/framework_templates.py` | Python functions that build the system prompt for Call 1 per framework + control vars |
| `backend/services/llm_client.py` | Thin wrapper around `google-genai`; mockable in tests |
| `backend/services/prompt_generator.py` | Call 1: sends framework template + inputs → returns `generated_prompt` string |
| `backend/services/planner.py` | Call 2: sends generated prompt → returns `PlannerResponse` |
| `backend/services/validator.py` | Plan Gate: validates plan against run config; returns `ValidationResult` |
| `backend/services/generator.py` | Call 3: sends validated plan → returns `AssessmentGenerationResponse` |

---

## Task 4: Framework Templates

**Files:**
- Create: `backend/services/__init__.py`
- Create: `backend/services/framework_templates.py`

The templates build the **system prompt** for Call 1. Call 1 asks the LLM to write an assessment prompt in a specific framework's structure. The control variables shape tone and length.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_framework_templates.py`:

```python
from backend.services.framework_templates import build_framework_system_prompt

def test_forge_template_contains_required_sections():
    prompt = build_framework_system_prompt(
        framework="forge",
        personality="formal",
        prompt_length="medium",
        result_length="medium",
        action_word_count=3,
    )
    for section in ["<context>", "<task>", "<constraints>", "<verification>", "<output_format>", "<reasoning_guidance>"]:
        assert section in prompt, f"Missing section: {section}"

def test_openai_template_contains_required_sections():
    prompt = build_framework_system_prompt(
        framework="openai",
        personality="socratic",
        prompt_length="short",
        result_length="long",
        action_word_count=2,
    )
    for section in ["# Role", "# Personality", "# Goal", "# Measure of Success", "# Constraints", "# Output", "# Stop Rules"]:
        assert section in prompt, f"Missing section: {section}"

def test_risen_template_contains_required_sections():
    prompt = build_framework_system_prompt(
        framework="risen",
        personality="encouraging",
        prompt_length="long",
        result_length="short",
        action_word_count=4,
    )
    for section in ["<role>", "<instructions>", "<step>", "<end_goal>", "<narrowing>"]:
        assert section in prompt, f"Missing section: {section}"

def test_personality_appears_in_prompt():
    prompt = build_framework_system_prompt(
        framework="forge", personality="socratic", prompt_length="medium",
        result_length="medium", action_word_count=3,
    )
    assert "socratic" in prompt.lower()

def test_invalid_framework_raises():
    import pytest
    with pytest.raises(ValueError, match="Unknown framework"):
        build_framework_system_prompt(
            framework="unknown", personality="formal", prompt_length="medium",
            result_length="medium", action_word_count=3,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_framework_templates.py -v`
Expected: `ImportError` — file doesn't exist yet.

- [ ] **Step 3: Create `backend/services/__init__.py`**

```python
```
(Empty)

- [ ] **Step 4: Create `backend/services/framework_templates.py`**

```python
_PERSONALITY_DESCRIPTIONS = {
    "formal": "Use a formal academic tone. Be precise, structured, and impersonal.",
    "socratic": "Use a Socratic questioning style. Guide learners to discover answers through probing questions rather than stating facts directly.",
    "encouraging": "Use an encouraging, supportive tone. Frame challenges positively and acknowledge effort.",
    "challenging": "Use a challenging, rigorous tone. Push learners to think deeper and justify every claim.",
}

_PROMPT_LENGTH_GUIDANCE = {
    "short": "approximately 150-250 words",
    "medium": "approximately 300-450 words",
    "long": "approximately 500-700 words",
}

_RESULT_LENGTH_GUIDANCE = {
    "short": "concise answers (1-2 sentences for MCQ distractors, 1-2 paragraphs for long answers)",
    "medium": "moderate answers (2-3 sentences for MCQ distractors, 2-3 paragraphs for long answers)",
    "long": "detailed answers (3-4 sentences for MCQ distractors, 3-4 paragraphs for long answers)",
}


def _forge_template(personality: str, prompt_length: str, result_length: str, action_word_count: int) -> str:
    return f"""You are an expert educational assessment designer. Generate an assessment prompt using the Forge framework with exactly these XML sections in order.

Personality instruction: {_PERSONALITY_DESCRIPTIONS[personality]}
Target prompt length: {_PROMPT_LENGTH_GUIDANCE[prompt_length]}
Expected answer length in generated assessment: {_RESULT_LENGTH_GUIDANCE[result_length]}
Use {action_word_count} distinct Bloom's taxonomy action verb(s) distributed across question topics.

Your output must be a single JSON object with key "generated_prompt" containing the complete prompt text. The prompt must contain all six sections:

<context>
[Domain background, course level, relevant technical context for the assessment topic]
</context>

<task>
[Clear statement of what questions the assessment must cover, using precise action verbs]
</task>

<constraints>
[Question type requirements: MCQ count and long answer count. Format constraints. Assumptions students should make.]
</constraints>

<verification>
[What the question generator should validate before finalizing: coverage of topics, Bloom level distribution, no repeated topics]
</verification>

<output_format>
[Exact JSON structure expected: questions array with type, body, options for MCQ, model_answer for long answer]
</output_format>

<reasoning_guidance>
[How to approach question construction: staged thinking, varying cognitive levels, distractor quality for MCQs]
</reasoning_guidance>

Return only valid JSON: {{"generated_prompt": "..."}}"""


def _openai_template(personality: str, prompt_length: str, result_length: str, action_word_count: int) -> str:
    return f"""You are an expert educational assessment designer. Generate an assessment prompt using the OpenAI prompt guidance framework with exactly these seven sections as Markdown headers.

Personality instruction: {_PERSONALITY_DESCRIPTIONS[personality]}
Target prompt length: {_PROMPT_LENGTH_GUIDANCE[prompt_length]}
Expected answer length in generated assessment: {_RESULT_LENGTH_GUIDANCE[result_length]}
Use {action_word_count} distinct Bloom's taxonomy action verb(s) distributed across question topics.

Your output must be a single JSON object with key "generated_prompt" containing the complete prompt text. The prompt must contain all seven sections:

# Role
[The AI's function as an assessment generator for this specific topic and course level]

# Personality
[Tone and collaboration style for how the AI should approach question construction]

# Goal
[Concrete deliverable: the structured assessment JSON with the specified question counts]

# Measure of Success
[Binary criteria that must be true before delivering the assessment: topic coverage, Bloom distribution, format compliance]

# Constraints
[Hard limits: question counts, no repeated topics, answer scope requirements, JSON format only]

# Output
[Exact JSON schema: questions array, MCQ option structure, model_answer field]

# Stop Rules
[When to abstain or retry: missing topic context, ambiguous expectations, schema validation failure]

Return only valid JSON: {{"generated_prompt": "..."}}"""


def _risen_template(personality: str, prompt_length: str, result_length: str, action_word_count: int) -> str:
    # Uses the spec's RISEN definition: Role, Instructions, Step, End_goal, Narrowing
    # NOTE: This differs from the RISEN skill (Role, Instruction, Structure, Examples, Nuance)
    return f"""You are an expert educational assessment designer. Generate an assessment prompt using the RISEN framework with exactly these five XML sections.

Personality instruction: {_PERSONALITY_DESCRIPTIONS[personality]}
Target prompt length: {_PROMPT_LENGTH_GUIDANCE[prompt_length]}
Expected answer length in generated assessment: {_RESULT_LENGTH_GUIDANCE[result_length]}
Use {action_word_count} distinct Bloom's taxonomy action verb(s) distributed across question topics.

Your output must be a single JSON object with key "generated_prompt" containing the complete prompt text. The prompt must contain all five sections:

<role>
[The AI's specific role and expertise for generating this type of educational assessment]
</role>

<instructions>
[Exact instructions for what the AI must produce: question types, counts, cognitive levels, topic distribution]
</instructions>

<step>
[Sequential steps the AI should follow when constructing the assessment: topic selection → cognitive mapping → question drafting → distractor construction]
</step>

<end_goal>
[The concrete outcome: a fully structured assessment JSON that meets all specified requirements]
</end_goal>

<narrowing>
[Scope constraints: what topics are in-bounds, Bloom level distribution limits, format restrictions, what to exclude]
</narrowing>

Return only valid JSON: {{"generated_prompt": "..."}}"""


_TEMPLATE_BUILDERS = {
    "forge": _forge_template,
    "openai": _openai_template,
    "risen": _risen_template,
}


def build_framework_system_prompt(
    framework: str,
    personality: str,
    prompt_length: str,
    result_length: str,
    action_word_count: int,
) -> str:
    builder = _TEMPLATE_BUILDERS.get(framework)
    if builder is None:
        raise ValueError(f"Unknown framework: {framework}. Must be one of: {list(_TEMPLATE_BUILDERS)}")
    return builder(personality, prompt_length, result_length, action_word_count)
```

- [ ] **Step 5: Run the tests**

Run: `pytest backend/tests/test_framework_templates.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/
git commit -m "feat: add framework template builders for Forge, OpenAI, and RISEN prompt frameworks"
```

---

## Task 5: LLM Client

**Files:**
- Create: `backend/services/llm_client.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_llm_client.py`:

```python
from unittest.mock import MagicMock, patch

def test_llm_client_calls_generate_content():
    with patch("backend.services.llm_client.genai.Client") as MockClient:
        mock_response = MagicMock()
        mock_response.text = '{"generated_prompt": "test prompt"}'
        MockClient.return_value.models.generate_content.return_value = mock_response

        from backend.services.llm_client import LLMClient
        client = LLMClient()
        result = client.generate(
            system_prompt="You are a test assistant.",
            user_message="Generate something.",
        )

        assert result == '{"generated_prompt": "test prompt"}'
        MockClient.return_value.models.generate_content.assert_called_once()

def test_llm_client_passes_model_name():
    with patch("backend.services.llm_client.genai.Client") as MockClient:
        mock_response = MagicMock()
        mock_response.text = "result"
        MockClient.return_value.models.generate_content.return_value = mock_response

        from backend.services.llm_client import LLMClient
        client = LLMClient(model="gemma-4-31b")
        client.generate("system", "user")

        call_kwargs = MockClient.return_value.models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == "gemma-4-31b"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_llm_client.py -v`
Expected: `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 3: Create `backend/services/llm_client.py`**

```python
import json
import re

from google import genai
from google.genai import types

from backend.config import settings


class LLMClient:
    def __init__(self, model: str | None = None):
        self.model = model or settings.llm_model
        self._client = genai.Client(api_key=settings.google_api_key)

    def generate(self, system_prompt: str, user_message: str) -> str:
        response = self._client.models.generate_content(
            model=self.model,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
            contents=user_message,
        )
        return response.text

    def generate_json(self, system_prompt: str, user_message: str) -> dict:
        text = self.generate(system_prompt, user_message)
        return _parse_json(text)


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if match:
        return json.loads(match.group(1))
    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        return json.loads(match.group(1))
    raise ValueError(f"Could not parse JSON from LLM response. First 300 chars: {text[:300]}")
```

- [ ] **Step 4: Run the tests**

Run: `pytest backend/tests/test_llm_client.py -v`
Expected: Both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/llm_client.py
git commit -m "feat: add LLM client wrapper with JSON extraction helper"
```

---

## Task 6: Prompt Generator — Call 1

**Files:**
- Create: `backend/services/prompt_generator.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prompt_generator.py`:

```python
from unittest.mock import MagicMock
import pytest
from backend.services.prompt_generator import generate_prompt

@pytest.fixture
def mock_llm():
    client = MagicMock()
    client.generate_json.return_value = {"generated_prompt": "You are an assessment generator. Topic: TCP/IP..."}
    return client

def test_generate_prompt_returns_string(mock_llm):
    result = generate_prompt(
        llm=mock_llm,
        topic="TCP/IP Networking",
        expectations="Test understanding of the three-way handshake",
        framework="forge",
        personality="formal",
        prompt_length="medium",
        result_length="medium",
        action_word_count=3,
        mcq_count=10,
        long_answer_count=3,
    )
    assert isinstance(result, str)
    assert len(result) > 0

def test_generate_prompt_calls_llm_with_framework_system_prompt(mock_llm):
    generate_prompt(
        llm=mock_llm,
        topic="TCP/IP Networking",
        expectations="Test handshake understanding",
        framework="forge",
        personality="formal",
        prompt_length="medium",
        result_length="medium",
        action_word_count=3,
        mcq_count=10,
        long_answer_count=3,
    )
    call_args = mock_llm.generate_json.call_args
    assert "<context>" in call_args.kwargs["system_prompt"]
    assert "TCP/IP Networking" in call_args.kwargs["user_message"]

def test_generate_prompt_raises_on_missing_key(mock_llm):
    mock_llm.generate_json.return_value = {"wrong_key": "value"}
    with pytest.raises(ValueError, match="generated_prompt"):
        generate_prompt(
            llm=mock_llm,
            topic="TCP/IP",
            expectations="test",
            framework="forge",
            personality="formal",
            prompt_length="medium",
            result_length="medium",
            action_word_count=3,
            mcq_count=10,
            long_answer_count=3,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_prompt_generator.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Create `backend/services/prompt_generator.py`**

```python
from backend.services.llm_client import LLMClient
from backend.services.framework_templates import build_framework_system_prompt


def generate_prompt(
    llm: LLMClient,
    topic: str,
    expectations: str,
    framework: str,
    personality: str,
    prompt_length: str,
    result_length: str,
    action_word_count: int,
    mcq_count: int,
    long_answer_count: int,
) -> str:
    system_prompt = build_framework_system_prompt(
        framework=framework,
        personality=personality,
        prompt_length=prompt_length,
        result_length=result_length,
        action_word_count=action_word_count,
    )
    user_message = (
        f"Topic: {topic}\n"
        f"Expectations: {expectations}\n"
        f"MCQ count: {mcq_count}\n"
        f"Long answer count: {long_answer_count}"
    )
    result = llm.generate_json(system_prompt=system_prompt, user_message=user_message)
    if "generated_prompt" not in result:
        raise ValueError(f"LLM response missing 'generated_prompt' key. Got keys: {list(result)}")
    return result["generated_prompt"]
```

- [ ] **Step 4: Run the tests**

Run: `pytest backend/tests/test_prompt_generator.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/prompt_generator.py
git commit -m "feat: add Call 1 prompt generator service"
```

---

## Task 7: Planner — Call 2

**Files:**
- Create: `backend/services/planner.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_planner.py`:

```python
from unittest.mock import MagicMock
import pytest
from backend.schemas.planner_schema import PlannerResponse
from backend.services.planner import generate_plan

VALID_PLAN_JSON = {
    "assessment_plan": {
        "questions": [
            {"type": "mcq", "bloom_level": "Analyze", "topic": "TCP Handshake", "answer_scope": "2-3 sentences"},
            {"type": "long_answer", "bloom_level": "Evaluate", "topic": "Congestion control", "answer_scope": "3 paragraphs"},
        ]
    }
}

@pytest.fixture
def mock_llm():
    client = MagicMock()
    client.generate_json.return_value = VALID_PLAN_JSON
    return client

def test_generate_plan_returns_planner_response(mock_llm):
    result = generate_plan(
        llm=mock_llm,
        generated_prompt="You are an assessment generator about TCP/IP...",
    )
    assert isinstance(result, PlannerResponse)
    assert len(result.assessment_plan.questions) == 2

def test_generate_plan_calls_llm_with_generated_prompt(mock_llm):
    generate_plan(llm=mock_llm, generated_prompt="Test prompt text")
    user_message = mock_llm.generate_json.call_args.kwargs["user_message"]
    assert "Test prompt text" in user_message

def test_generate_plan_raises_on_invalid_llm_response(mock_llm):
    mock_llm.generate_json.return_value = {"wrong_structure": {}}
    with pytest.raises(Exception):
        generate_plan(llm=mock_llm, generated_prompt="test")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_planner.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Create `backend/services/planner.py`**

```python
from backend.schemas.planner_schema import PlannerResponse
from backend.services.llm_client import LLMClient

_PLANNER_SYSTEM_PROMPT = """You are a structured assessment planner. Given an assessment prompt, produce a planning document that outlines the structure of every question before any question text is written.

For each question, specify:
- type: "mcq" or "long_answer"
- bloom_level: the Bloom's taxonomy action word (e.g., "Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create")
- topic: the specific sub-topic this question tests (unique — no two questions may share the same topic)
- answer_scope: a brief description of the expected answer length and depth

Return only valid JSON matching this schema exactly:
{
  "assessment_plan": {
    "questions": [
      {"type": "mcq", "bloom_level": "...", "topic": "...", "answer_scope": "..."}
    ]
  }
}"""


def generate_plan(llm: LLMClient, generated_prompt: str) -> PlannerResponse:
    user_message = f"Assessment prompt to plan:\n\n{generated_prompt}"
    raw = llm.generate_json(system_prompt=_PLANNER_SYSTEM_PROMPT, user_message=user_message)
    return PlannerResponse(**raw)
```

- [ ] **Step 4: Run the tests**

Run: `pytest backend/tests/test_planner.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/planner.py
git commit -m "feat: add Call 2 planner service"
```

---

## Task 8: Validator — Plan Gate

**Files:**
- Create: `backend/services/validator.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_validator.py`:

```python
import pytest
from backend.schemas.planner_schema import PlannerResponse
from backend.services.validator import validate_plan, ValidationResult

def _make_plan(questions):
    return PlannerResponse(assessment_plan={"questions": questions})

def _mcq(topic, bloom="Analyze"):
    return {"type": "mcq", "bloom_level": bloom, "topic": topic, "answer_scope": "2 sentences"}

def _la(topic, bloom="Evaluate"):
    return {"type": "long_answer", "bloom_level": bloom, "topic": topic, "answer_scope": "3 paragraphs"}

def test_valid_plan_passes():
    questions = [_mcq(f"Topic {i}") for i in range(10)] + [_la(f"LA Topic {i}") for i in range(3)]
    plan = _make_plan(questions)
    result = validate_plan(plan, mcq_count=10, long_answer_count=3)
    assert result.passed is True
    assert result.errors == []

def test_wrong_mcq_count_fails():
    questions = [_mcq(f"Topic {i}") for i in range(8)] + [_la(f"LA Topic {i}") for i in range(3)]
    plan = _make_plan(questions)
    result = validate_plan(plan, mcq_count=10, long_answer_count=3)
    assert result.passed is False
    assert any("MCQ" in e for e in result.errors)

def test_wrong_long_answer_count_fails():
    questions = [_mcq(f"Topic {i}") for i in range(10)] + [_la(f"LA Topic {i}") for i in range(2)]
    plan = _make_plan(questions)
    result = validate_plan(plan, mcq_count=10, long_answer_count=3)
    assert result.passed is False
    assert any("long answer" in e.lower() for e in result.errors)

def test_repeated_topic_fails():
    questions = [_mcq("TCP Handshake") for _ in range(10)] + [_la(f"LA Topic {i}") for i in range(3)]
    plan = _make_plan(questions)
    result = validate_plan(plan, mcq_count=10, long_answer_count=3)
    assert result.passed is False
    assert any("repeated" in e.lower() for e in result.errors)

def test_bloom_concentration_fails():
    # All 10 MCQs use "Analyze" — that's 77% of 13 questions, exceeds 60%
    questions = [_mcq(f"Topic {i}", bloom="Analyze") for i in range(10)] + [_la(f"LA Topic {i}") for i in range(3)]
    plan = _make_plan(questions)
    result = validate_plan(plan, mcq_count=10, long_answer_count=3)
    assert result.passed is False
    assert any("bloom" in e.lower() or "60%" in e for e in result.errors)

def test_empty_answer_scope_fails():
    questions = (
        [_mcq(f"Topic {i}") for i in range(9)]
        + [{"type": "mcq", "bloom_level": "Apply", "topic": "Topic 9", "answer_scope": ""}]
        + [_la(f"LA Topic {i}") for i in range(3)]
    )
    plan = _make_plan(questions)
    result = validate_plan(plan, mcq_count=10, long_answer_count=3)
    assert result.passed is False
    assert any("answer_scope" in e.lower() or "empty" in e.lower() for e in result.errors)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_validator.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Create `backend/services/validator.py`**

```python
from collections import Counter
from dataclasses import dataclass, field
from backend.schemas.planner_schema import PlannerResponse


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)


def validate_plan(plan: PlannerResponse, mcq_count: int, long_answer_count: int) -> ValidationResult:
    errors = []
    questions = plan.assessment_plan.questions

    actual_mcq = sum(1 for q in questions if q.type == "mcq")
    actual_la = sum(1 for q in questions if q.type == "long_answer")

    if actual_mcq != mcq_count:
        errors.append(f"MCQ count mismatch: expected {mcq_count}, got {actual_mcq}")

    if actual_la != long_answer_count:
        errors.append(f"Long answer count mismatch: expected {long_answer_count}, got {actual_la}")

    topics = [q.topic.strip().lower() for q in questions]
    topic_counts = Counter(topics)
    repeated = [t for t, count in topic_counts.items() if count > 1]
    if repeated:
        errors.append(f"Repeated question topics: {repeated}")

    total = len(questions)
    if total > 0:
        bloom_counts = Counter(q.bloom_level.strip().lower() for q in questions)
        for level, count in bloom_counts.items():
            if count / total > 0.60:
                errors.append(
                    f"Bloom level '{level}' appears in {count}/{total} questions ({count/total:.0%}), exceeds 60% limit"
                )

    empty_scope = [i + 1 for i, q in enumerate(questions) if not q.answer_scope.strip()]
    if empty_scope:
        errors.append(f"Empty answer_scope on question(s): {empty_scope}")

    return ValidationResult(passed=len(errors) == 0, errors=errors)
```

- [ ] **Step 4: Run the tests**

Run: `pytest backend/tests/test_validator.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/validator.py
git commit -m "feat: add plan gate validator for question count, topic uniqueness, Bloom distribution"
```

---

## Task 9: Generator — Call 3

**Files:**
- Create: `backend/services/generator.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_generator.py`:

```python
from unittest.mock import MagicMock
import pytest
from backend.schemas.planner_schema import PlannerResponse
from backend.schemas.assessment_schema import AssessmentGenerationResponse
from backend.services.generator import generate_assessment

VALID_PLAN = PlannerResponse(assessment_plan={"questions": [
    {"type": "mcq", "bloom_level": "Analyze", "topic": "TCP Handshake", "answer_scope": "2 sentences"},
    {"type": "long_answer", "bloom_level": "Evaluate", "topic": "Congestion control", "answer_scope": "3 paragraphs"},
]})

VALID_GENERATION_JSON = {
    "questions": [
        {
            "type": "mcq",
            "body": "What is the purpose of the SYN flag?",
            "options": [
                {"body": "Initiate a connection", "is_correct": True},
                {"body": "Terminate a connection", "is_correct": False},
                {"body": "Acknowledge data", "is_correct": False},
                {"body": "Request retransmission", "is_correct": False},
            ],
            "model_answer": None,
        },
        {
            "type": "long_answer",
            "body": "Explain TCP congestion control mechanisms.",
            "options": [],
            "model_answer": "TCP uses slow start, congestion avoidance, fast retransmit...",
        },
    ]
}

@pytest.fixture
def mock_llm():
    client = MagicMock()
    client.generate_json.return_value = VALID_GENERATION_JSON
    return client

def test_generate_assessment_returns_response(mock_llm):
    result = generate_assessment(llm=mock_llm, plan=VALID_PLAN)
    assert isinstance(result, AssessmentGenerationResponse)
    assert len(result.questions) == 2

def test_mcq_has_four_options(mock_llm):
    result = generate_assessment(llm=mock_llm, plan=VALID_PLAN)
    mcq = result.questions[0]
    assert mcq.type == "mcq"
    assert len(mcq.options) == 4
    assert sum(1 for o in mcq.options if o.is_correct) == 1

def test_long_answer_has_model_answer(mock_llm):
    result = generate_assessment(llm=mock_llm, plan=VALID_PLAN)
    la = result.questions[1]
    assert la.type == "long_answer"
    assert la.model_answer is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_generator.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Create `backend/services/generator.py`**

```python
import json
from backend.schemas.planner_schema import PlannerResponse
from backend.schemas.assessment_schema import AssessmentGenerationResponse
from backend.services.llm_client import LLMClient

_GENERATOR_SYSTEM_PROMPT = """You are an expert educational assessment writer. Given a structured assessment plan, write all questions in full.

For MCQ questions:
- Write a clear, unambiguous question body
- Provide exactly 4 options: exactly one must be correct (is_correct: true), three must be plausible distractors
- Set model_answer to null

For long answer questions:
- Write a clear, open-ended question body
- Set options to an empty array []
- Write a complete model answer appropriate to the answer_scope in the plan

Return only valid JSON matching this schema:
{
  "questions": [
    {
      "type": "mcq",
      "body": "...",
      "options": [{"body": "...", "is_correct": false}, ...],
      "model_answer": null
    },
    {
      "type": "long_answer",
      "body": "...",
      "options": [],
      "model_answer": "..."
    }
  ]
}

Generate questions in the same order as the plan. Do not skip any question."""


def generate_assessment(llm: LLMClient, plan: PlannerResponse) -> AssessmentGenerationResponse:
    plan_text = json.dumps(plan.model_dump(), indent=2)
    user_message = f"Assessment plan to execute:\n\n{plan_text}"
    raw = llm.generate_json(system_prompt=_GENERATOR_SYSTEM_PROMPT, user_message=user_message)
    return AssessmentGenerationResponse(**raw)
```

- [ ] **Step 4: Run the tests**

Run: `pytest backend/tests/test_generator.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Run all tests to confirm no regressions**

Run: `pytest backend/tests/ -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/generator.py
git commit -m "feat: add Call 3 generator service"
```
