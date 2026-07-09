# Assessment Generator — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI + Celery backend that accepts a run configuration, executes 12 parallel 3-call LLM assessment pipelines, streams SSE progress, and exports PDFs.

**Architecture:** FastAPI serves the REST + SSE API. Celery workers execute the 3-call pipeline (Prompt Generator → Planner → Validator → Generator) for each of the 12 assessments in parallel. Redis serves as the Celery broker, result backend, and SSE relay channel (workers publish events; the SSE route subscribes). SQLite stores all records.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, Celery 5.x, Redis, `google-genai`, `sse-starlette`, `redis-py`, WeasyPrint, pytest

---

## File Map

| File | Responsibility |
|---|---|
| `backend/config.py` | Settings from env vars (API key, Redis URL, SQLite path, LLM model) |
| `backend/database.py` | SQLAlchemy engine, session factory, `get_db` dependency |
| `backend/celery_app.py` | Celery app instance with Redis broker |
| `backend/main.py` | FastAPI app, CORS, router registration |
| `backend/models/run.py` | `Run`, `ControlSet` ORM models |
| `backend/models/assessment.py` | `Assessment`, `PromptGeneration`, `PlannerOutput`, `AssessmentGeneration` ORM models |
| `backend/models/question.py` | `Question`, `MCQOption`, `ModelAnswer` ORM models |
| `backend/schemas/run_schemas.py` | Pydantic shapes for run create/response |
| `backend/schemas/prompt_schema.py` | Pydantic shape for Call 1 output |
| `backend/schemas/planner_schema.py` | Pydantic shapes for Call 2 output (plan + question plans) |
| `backend/schemas/assessment_schema.py` | Pydantic shapes for Call 3 output |
| `backend/services/llm_client.py` | Thin wrapper around `google-genai`; mockable in tests |
| `backend/services/framework_templates.py` | Python functions that build the system prompt for Call 1 per framework + control vars |
| `backend/services/prompt_generator.py` | Call 1: sends framework template + inputs → returns `generated_prompt` |
| `backend/services/planner.py` | Call 2: sends generated prompt → returns structured question plan |
| `backend/services/validator.py` | Plan Gate: validates plan against run config; returns pass/fail + errors |
| `backend/services/generator.py` | Call 3: sends validated plan → returns full question set |
| `backend/workers/assessment_worker.py` | Celery task: chains all 4 stages for one assessment, writes DB records, publishes SSE events |
| `backend/api/runs.py` | `POST /runs` (SSE stream) and `GET /runs/{id}` |
| `backend/api/assessments.py` | `GET /assessments/{id}`, `POST /assessments/{id}/regenerate`, `POST /assessments/{id}/export-pdf` |
| `backend/templates/pdf/student.html` | WeasyPrint template: questions only |
| `backend/templates/pdf/answer_key.html` | WeasyPrint template: questions + answers |
| `backend/tests/conftest.py` | pytest fixtures: in-memory SQLite DB, TestClient, mock LLM |

---

## Task 1: Project Setup + Config

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/config.py`
- Create: `backend/database.py`
- Create: `backend/main.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create `backend/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.35
celery==5.4.0
redis==5.1.1
sse-starlette==2.1.3
google-genai==1.3.0
weasyprint==62.3
pydantic==2.9.2
pydantic-settings==2.5.2
python-multipart==0.0.12
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -r backend/requirements.txt`
Expected: All packages install without errors.

- [ ] **Step 3: Create `backend/config.py`**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    google_api_key: str
    llm_model: str = "gemma-4-31b"
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite:///./assessment_generator.db"

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 4: Create `backend/database.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 5: Create `backend/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Assessment Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Write the health check test**

In `backend/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, get_db
from backend.main import app

TEST_DATABASE_URL = "sqlite://"

@pytest.fixture(scope="function")
def test_db():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(test_db):
    def override_get_db():
        yield test_db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

In `backend/tests/test_main.py`:

```python
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `pytest backend/tests/test_main.py -v`
Expected: `test_health PASSED`

- [ ] **Step 8: Create `.env` file at repo root**

```
GOOGLE_API_KEY=your_key_here
LLM_MODEL=gemma-4-31b
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=sqlite:///./assessment_generator.db
```

- [ ] **Step 9: Commit**

```bash
git add backend/requirements.txt backend/config.py backend/database.py backend/main.py backend/tests/
git commit -m "feat: scaffold backend project with FastAPI, SQLAlchemy, and health endpoint"
```

---

## Task 2: SQLAlchemy Models

**Files:**
- Create: `backend/models/__init__.py`
- Create: `backend/models/run.py`
- Create: `backend/models/assessment.py`
- Create: `backend/models/question.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_models.py`:

```python
from backend.models.run import Run, ControlSet
from backend.models.assessment import Assessment, PromptGeneration, PlannerOutput, AssessmentGeneration
from backend.models.question import Question, MCQOption, ModelAnswer

def test_create_run(test_db):
    run = Run(topic="TCP/IP", expectations="Test understanding of handshake", mcq_count=10, long_answer_count=3)
    test_db.add(run)
    test_db.commit()
    assert run.id is not None

def test_create_control_set(test_db):
    run = Run(topic="TCP/IP", expectations="Test handshake", mcq_count=10, long_answer_count=3)
    test_db.add(run)
    test_db.commit()
    cs = ControlSet(run_id=run.id, personality="formal", prompt_length="medium", result_length="medium", action_word_count=3)
    test_db.add(cs)
    test_db.commit()
    assert cs.id is not None
    assert cs.run_id == run.id

def test_create_assessment(test_db):
    run = Run(topic="TCP/IP", expectations="Test handshake", mcq_count=10, long_answer_count=3)
    test_db.add(run)
    test_db.commit()
    cs = ControlSet(run_id=run.id, personality="formal", prompt_length="medium", result_length="medium", action_word_count=3)
    test_db.add(cs)
    test_db.commit()
    a = Assessment(run_id=run.id, framework="forge", control_set_id=cs.id, status="pending")
    test_db.add(a)
    test_db.commit()
    assert a.id is not None
    assert a.status == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_models.py -v`
Expected: `ImportError` or `ModuleNotFoundError` — models don't exist yet.

- [ ] **Step 3: Create `backend/models/__init__.py`**

```python
```
(Empty file)

- [ ] **Step 4: Create `backend/models/run.py`**

```python
from datetime import datetime, timezone
from sqlalchemy import Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base

class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    expectations: Mapped[str] = mapped_column(String, nullable=False)
    mcq_count: Mapped[int] = mapped_column(Integer, default=10)
    long_answer_count: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    control_sets: Mapped[list["ControlSet"]] = relationship("ControlSet", back_populates="run")
    assessments: Mapped[list["Assessment"]] = relationship("Assessment", back_populates="run")

class ControlSet(Base):
    __tablename__ = "control_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("runs.id"), nullable=False)
    personality: Mapped[str] = mapped_column(String, nullable=False)
    prompt_length: Mapped[str] = mapped_column(String, nullable=False)
    result_length: Mapped[str] = mapped_column(String, nullable=False)
    action_word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    run: Mapped["Run"] = relationship("Run", back_populates="control_sets")
```

- [ ] **Step 5: Create `backend/models/assessment.py`**

```python
from datetime import datetime, timezone
from sqlalchemy import Integer, String, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base

class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("runs.id"), nullable=False)
    framework: Mapped[str] = mapped_column(String, nullable=False)
    control_set_id: Mapped[int] = mapped_column(Integer, ForeignKey("control_sets.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    run: Mapped["Run"] = relationship("Run", back_populates="assessments")
    prompt_generation: Mapped["PromptGeneration"] = relationship("PromptGeneration", back_populates="assessment", uselist=False)
    planner_output: Mapped["PlannerOutput"] = relationship("PlannerOutput", back_populates="assessment", uselist=False)
    assessment_generation: Mapped["AssessmentGeneration"] = relationship("AssessmentGeneration", back_populates="assessment", uselist=False)
    questions: Mapped[list["Question"]] = relationship("Question", back_populates="assessment")

class PromptGeneration(Base):
    __tablename__ = "prompt_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessments.id"), nullable=False)
    prompt_text: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="prompt_generation")

class PlannerOutput(Base):
    __tablename__ = "planner_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessments.id"), nullable=False)
    plan_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validation_errors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="planner_output")

class AssessmentGeneration(Base):
    __tablename__ = "assessment_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessments.id"), nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="assessment_generation")
```

- [ ] **Step 6: Create `backend/models/question.py`**

```python
from sqlalchemy import Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base

class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assessments.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)

    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="questions")
    options: Mapped[list["MCQOption"]] = relationship("MCQOption", back_populates="question")
    model_answer: Mapped["ModelAnswer"] = relationship("ModelAnswer", back_populates="question", uselist=False)

class MCQOption(Base):
    __tablename__ = "mcq_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)

    question: Mapped["Question"] = relationship("Question", back_populates="options")

class ModelAnswer(Base):
    __tablename__ = "model_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("questions.id"), nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)

    question: Mapped["Question"] = relationship("Question", back_populates="model_answer")
```

- [ ] **Step 7: Update `conftest.py` to import all models so `Base.metadata.create_all` picks them up**

Add to the top of `backend/tests/conftest.py`:

```python
import backend.models.run  # noqa: F401
import backend.models.assessment  # noqa: F401
import backend.models.question  # noqa: F401
```

And update `backend/models/assessment.py` to import `Question` for the relationship:

Add to top of `assessment.py`:
```python
from backend.models.question import Question  # noqa: F401
```

Add to top of `run.py`:
```python
from backend.models.assessment import Assessment  # noqa: F401
```

- [ ] **Step 8: Run the tests**

Run: `pytest backend/tests/test_models.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/models/
git commit -m "feat: add SQLAlchemy ORM models for all data entities"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Create: `backend/schemas/__init__.py`
- Create: `backend/schemas/run_schemas.py`
- Create: `backend/schemas/prompt_schema.py`
- Create: `backend/schemas/planner_schema.py`
- Create: `backend/schemas/assessment_schema.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError
from backend.schemas.prompt_schema import PromptGenerationResponse
from backend.schemas.planner_schema import PlannerResponse, QuestionPlan
from backend.schemas.assessment_schema import AssessmentGenerationResponse, MCQOptionSchema, QuestionResponse

def test_prompt_schema_valid():
    r = PromptGenerationResponse(generated_prompt="Generate questions about TCP/IP...")
    assert r.generated_prompt == "Generate questions about TCP/IP..."

def test_prompt_schema_missing_field():
    with pytest.raises(ValidationError):
        PromptGenerationResponse()

def test_planner_schema_valid():
    plan_data = {
        "assessment_plan": {
            "questions": [
                {"type": "mcq", "bloom_level": "Analyze", "topic": "TCP Handshake", "answer_scope": "2-3 sentences"},
                {"type": "long_answer", "bloom_level": "Evaluate", "topic": "Congestion control", "answer_scope": "3-4 paragraphs"},
            ]
        }
    }
    r = PlannerResponse(**plan_data)
    assert len(r.assessment_plan.questions) == 2
    assert r.assessment_plan.questions[0].type == "mcq"

def test_planner_schema_invalid_type():
    with pytest.raises(ValidationError):
        PlannerResponse(assessment_plan={"questions": [{"type": "essay", "bloom_level": "X", "topic": "Y", "answer_scope": "Z"}]})

def test_assessment_schema_valid():
    data = {
        "questions": [
            {
                "type": "mcq",
                "body": "What does SYN stand for?",
                "options": [
                    {"body": "Synchronize", "is_correct": True},
                    {"body": "System", "is_correct": False},
                    {"body": "Signal", "is_correct": False},
                    {"body": "Send", "is_correct": False},
                ],
                "model_answer": None,
            }
        ]
    }
    r = AssessmentGenerationResponse(**data)
    assert r.questions[0].type == "mcq"
    assert r.questions[0].options[0].is_correct is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_schemas.py -v`
Expected: `ImportError` — schemas don't exist yet.

- [ ] **Step 3: Create `backend/schemas/__init__.py`**

```python
```
(Empty)

- [ ] **Step 4: Create `backend/schemas/prompt_schema.py`**

```python
from pydantic import BaseModel

class PromptGenerationResponse(BaseModel):
    generated_prompt: str
```

- [ ] **Step 5: Create `backend/schemas/planner_schema.py`**

```python
from typing import Literal
from pydantic import BaseModel

class QuestionPlan(BaseModel):
    type: Literal["mcq", "long_answer"]
    bloom_level: str
    topic: str
    answer_scope: str

class AssessmentPlan(BaseModel):
    questions: list[QuestionPlan]

class PlannerResponse(BaseModel):
    assessment_plan: AssessmentPlan
```

- [ ] **Step 6: Create `backend/schemas/assessment_schema.py`**

```python
from typing import Literal
from pydantic import BaseModel

class MCQOptionSchema(BaseModel):
    body: str
    is_correct: bool

class QuestionResponse(BaseModel):
    type: Literal["mcq", "long_answer"]
    body: str
    options: list[MCQOptionSchema]
    model_answer: str | None

class AssessmentGenerationResponse(BaseModel):
    questions: list[QuestionResponse]
```

- [ ] **Step 7: Create `backend/schemas/run_schemas.py`**

```python
from datetime import datetime
from pydantic import BaseModel, Field

class ControlSetCreate(BaseModel):
    personality: str
    prompt_length: str
    result_length: str
    action_word_count: int = Field(ge=1, le=5)

class RunCreate(BaseModel):
    topic: str
    expectations: str
    mcq_count: int = Field(default=10, ge=1)
    long_answer_count: int = Field(default=3, ge=1)
    control_sets: list[ControlSetCreate] = Field(min_length=4, max_length=4)
    frameworks: list[str] = Field(default=["forge", "openai", "risen"])

class ControlSetResponse(BaseModel):
    id: int
    personality: str
    prompt_length: str
    result_length: str
    action_word_count: int

    model_config = {"from_attributes": True}

class AssessmentSummary(BaseModel):
    id: int
    framework: str
    control_set_id: int
    status: str

    model_config = {"from_attributes": True}

class RunResponse(BaseModel):
    id: int
    topic: str
    expectations: str
    mcq_count: int
    long_answer_count: int
    created_at: datetime
    control_sets: list[ControlSetResponse]
    assessments: list[AssessmentSummary]

    model_config = {"from_attributes": True}
```

- [ ] **Step 8: Run the tests**

Run: `pytest backend/tests/test_schemas.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/schemas/
git commit -m "feat: add Pydantic schemas for LLM I/O validation and API request/response shapes"
```

---

## Task 4: Framework Templates

**Files:**
- Create: `backend/services/__init__.py`
- Create: `backend/services/framework_templates.py`

The templates build the **system prompt** for Call 1 (Prompt Generator). Call 1 asks Gemma to write an assessment prompt in a specific framework's structure. The control variables shape tone and length.

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
    questions = [_mcq(f"Topic {i}") for i in range(9)] + [{"type": "mcq", "bloom_level": "Apply", "topic": "Topic 9", "answer_scope": ""}] + [_la(f"LA Topic {i}") for i in range(3)]
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
from backend.schemas.planner_schema import PlannerResponse
from backend.schemas.assessment_schema import AssessmentGenerationResponse
from backend.services.llm_client import LLMClient
import json

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

- [ ] **Step 5: Commit**

```bash
git add backend/services/generator.py
git commit -m "feat: add Call 3 generator service"
```

---

## Task 10: Celery App + Assessment Worker

**Files:**
- Create: `backend/celery_app.py`
- Create: `backend/workers/__init__.py`
- Create: `backend/workers/assessment_worker.py`

The worker executes all four stages for one assessment, writes records at each stage, publishes SSE progress events to Redis, and transitions the `Assessment.status` field at each stage.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_worker.py`:

```python
from unittest.mock import MagicMock, patch
import pytest
from backend.models.run import Run, ControlSet
from backend.models.assessment import Assessment

@pytest.fixture
def run_with_assessment(test_db):
    run = Run(topic="TCP/IP", expectations="Test handshake", mcq_count=2, long_answer_count=1)
    test_db.add(run)
    test_db.commit()
    cs = ControlSet(run_id=run.id, personality="formal", prompt_length="medium", result_length="medium", action_word_count=2)
    test_db.add(cs)
    test_db.commit()
    a = Assessment(run_id=run.id, framework="forge", control_set_id=cs.id, status="pending")
    test_db.add(a)
    test_db.commit()
    return a, run, cs

MOCK_PROMPT_JSON = {"generated_prompt": "You are a test prompt..."}
MOCK_PLAN_JSON = {
    "assessment_plan": {
        "questions": [
            {"type": "mcq", "bloom_level": "Analyze", "topic": "SYN Flag", "answer_scope": "1 sentence"},
            {"type": "mcq", "bloom_level": "Apply", "topic": "ACK Flag", "answer_scope": "1 sentence"},
            {"type": "long_answer", "bloom_level": "Evaluate", "topic": "Congestion", "answer_scope": "2 paragraphs"},
        ]
    }
}
MOCK_GENERATION_JSON = {
    "questions": [
        {"type": "mcq", "body": "Q1?", "options": [{"body": "A", "is_correct": True}, {"body": "B", "is_correct": False}, {"body": "C", "is_correct": False}, {"body": "D", "is_correct": False}], "model_answer": None},
        {"type": "mcq", "body": "Q2?", "options": [{"body": "A", "is_correct": False}, {"body": "B", "is_correct": True}, {"body": "C", "is_correct": False}, {"body": "D", "is_correct": False}], "model_answer": None},
        {"type": "long_answer", "body": "Q3?", "options": [], "model_answer": "Model answer here."},
    ]
}

def test_pipeline_sets_status_complete(run_with_assessment, test_db):
    assessment, run, cs = run_with_assessment

    with patch("backend.workers.assessment_worker.LLMClient") as MockLLM, \
         patch("backend.workers.assessment_worker.SessionLocal") as MockSession, \
         patch("backend.workers.assessment_worker.redis_client") as mock_redis:

        MockSession.return_value.__enter__ = lambda s: test_db
        MockSession.return_value.__exit__ = MagicMock(return_value=False)

        mock_llm_instance = MagicMock()
        mock_llm_instance.generate_json.side_effect = [
            MOCK_PROMPT_JSON,
            MOCK_PLAN_JSON,
            MOCK_GENERATION_JSON,
        ]
        MockLLM.return_value = mock_llm_instance

        from backend.workers.assessment_worker import run_assessment_pipeline
        run_assessment_pipeline(assessment.id)

        test_db.refresh(assessment)
        assert assessment.status == "complete"

def test_pipeline_sets_error_on_validation_failure(run_with_assessment, test_db):
    assessment, run, cs = run_with_assessment

    bad_plan = {
        "assessment_plan": {
            "questions": [
                # Only 1 MCQ but run expects 2 — validation should fail
                {"type": "mcq", "bloom_level": "Analyze", "topic": "SYN Flag", "answer_scope": "1 sentence"},
                {"type": "long_answer", "bloom_level": "Evaluate", "topic": "Congestion", "answer_scope": "2 paragraphs"},
            ]
        }
    }

    with patch("backend.workers.assessment_worker.LLMClient") as MockLLM, \
         patch("backend.workers.assessment_worker.SessionLocal") as MockSession, \
         patch("backend.workers.assessment_worker.redis_client") as mock_redis:

        MockSession.return_value.__enter__ = lambda s: test_db
        MockSession.return_value.__exit__ = MagicMock(return_value=False)

        mock_llm_instance = MagicMock()
        mock_llm_instance.generate_json.side_effect = [MOCK_PROMPT_JSON, bad_plan]
        MockLLM.return_value = mock_llm_instance

        from backend.workers.assessment_worker import run_assessment_pipeline
        run_assessment_pipeline(assessment.id)

        test_db.refresh(assessment)
        assert assessment.status == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_worker.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Create `backend/celery_app.py`**

```python
from celery import Celery
from backend.config import settings

celery_app = Celery(
    "assessment_generator",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["backend.workers.assessment_worker"],
)

celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
```

- [ ] **Step 4: Create `backend/workers/__init__.py`**

```python
```
(Empty)

- [ ] **Step 5: Create `backend/workers/assessment_worker.py`**

```python
import json
import redis
from contextlib import contextmanager
from sqlalchemy.orm import Session

from backend.celery_app import celery_app
from backend.config import settings
from backend.database import SessionLocal
from backend.models.assessment import Assessment, PromptGeneration, PlannerOutput, AssessmentGeneration
from backend.models.question import Question, MCQOption, ModelAnswer
from backend.services.llm_client import LLMClient
from backend.services.prompt_generator import generate_prompt
from backend.services.planner import generate_plan
from backend.services.validator import validate_plan
from backend.services.generator import generate_assessment

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _publish_progress(run_id: int, assessment_id: int, framework: str, control_set_id: int, stage: str):
    event = json.dumps({
        "assessment_id": assessment_id,
        "framework": framework,
        "control_set": control_set_id,
        "stage": stage,
    })
    redis_client.publish(f"run:{run_id}:progress", event)


def _set_status(db: Session, assessment: Assessment, status: str):
    assessment.status = status
    db.commit()


@celery_app.task(bind=True, max_retries=3)
def run_assessment_pipeline(self, assessment_id: int):
    with SessionLocal() as db:
        assessment = db.get(Assessment, assessment_id)
        if assessment is None:
            return
        run = assessment.run
        control_set = assessment.control_set

        try:
            llm = LLMClient()

            # Stage 1: Prompt generation
            _set_status(db, assessment, "prompting")
            _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "prompting")

            prompt_text = generate_prompt(
                llm=llm,
                topic=run.topic,
                expectations=run.expectations,
                framework=assessment.framework,
                personality=control_set.personality,
                prompt_length=control_set.prompt_length,
                result_length=control_set.result_length,
                action_word_count=control_set.action_word_count,
                mcq_count=run.mcq_count,
                long_answer_count=run.long_answer_count,
            )
            db.add(PromptGeneration(assessment_id=assessment_id, prompt_text=prompt_text))
            db.commit()

            # Stage 2: Planning
            _set_status(db, assessment, "planning")
            _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "planning")

            plan = generate_plan(llm=llm, generated_prompt=prompt_text)

            # Stage 3: Validation
            _set_status(db, assessment, "validating")
            _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "validating")

            validation = validate_plan(plan, mcq_count=run.mcq_count, long_answer_count=run.long_answer_count)
            db.add(PlannerOutput(
                assessment_id=assessment_id,
                plan_json=plan.model_dump(),
                validation_passed=validation.passed,
                validation_errors=validation.errors if not validation.passed else None,
            ))
            db.commit()

            if not validation.passed:
                _set_status(db, assessment, "error")
                _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "error")
                return

            # Stage 4: Generation
            _set_status(db, assessment, "generating")
            _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "generating")

            generated = generate_assessment(llm=llm, plan=plan)
            db.add(AssessmentGeneration(assessment_id=assessment_id, raw_json=generated.model_dump()))
            db.commit()

            for order, q in enumerate(generated.questions):
                question = Question(
                    assessment_id=assessment_id,
                    type=q.type,
                    body=q.body,
                    order=order,
                )
                db.add(question)
                db.flush()

                if q.type == "mcq":
                    for opt in q.options:
                        db.add(MCQOption(question_id=question.id, body=opt.body, is_correct=opt.is_correct))
                elif q.type == "long_answer" and q.model_answer:
                    db.add(ModelAnswer(question_id=question.id, body=q.model_answer))

            db.commit()

            _set_status(db, assessment, "complete")
            _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "complete")

        except Exception as exc:
            _set_status(db, assessment, "error")
            _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "error")
            raise self.retry(exc=exc, countdown=10)
```

- [ ] **Step 6: Update `SessionLocal` to support context manager**

In `backend/database.py`, update `SessionLocal`:

```python
from contextlib import contextmanager

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Replace the bare sessionmaker with a context-manager wrapper for worker use
class _SessionFactory:
    def __call__(self):
        return SessionLocal()
    
    def __enter__(self):
        self._session = SessionLocal()
        return self._session
    
    def __exit__(self, *args):
        self._session.close()
```

Actually, use the simpler approach: wrap where needed. In `assessment_worker.py`, replace `with SessionLocal() as db:` with:

```python
db = SessionLocal()
try:
    ...
finally:
    db.close()
```

And update the test mock accordingly.

- [ ] **Step 7: Run the tests**

Run: `pytest backend/tests/test_worker.py -v`
Expected: Both tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/celery_app.py backend/workers/
git commit -m "feat: add Celery app and assessment pipeline worker with SSE progress publishing"
```

---

## Task 11: Runs API — POST /runs (SSE) + GET /runs/{id}

**Files:**
- Create: `backend/api/__init__.py`
- Create: `backend/api/runs.py`
- Modify: `backend/main.py`

The POST `/runs` endpoint creates all DB records, enqueues 12 Celery tasks, then returns an `EventSourceResponse` that subscribes to the Redis pub/sub channel for that run and streams events until all 12 assessments are terminal.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_api_runs.py`:

```python
from unittest.mock import patch, MagicMock

RUN_PAYLOAD = {
    "topic": "TCP/IP Networking",
    "expectations": "Test understanding of the three-way handshake",
    "mcq_count": 2,
    "long_answer_count": 1,
    "control_sets": [
        {"personality": "formal", "prompt_length": "short", "result_length": "short", "action_word_count": 2},
        {"personality": "socratic", "prompt_length": "medium", "result_length": "medium", "action_word_count": 3},
        {"personality": "encouraging", "prompt_length": "long", "result_length": "long", "action_word_count": 4},
        {"personality": "challenging", "prompt_length": "short", "result_length": "medium", "action_word_count": 1},
    ],
    "frameworks": ["forge", "openai", "risen"],
}

def test_get_run_not_found(client):
    response = client.get("/runs/999")
    assert response.status_code == 404

def test_get_run_returns_run(client, test_db):
    from backend.models.run import Run
    run = Run(topic="Test", expectations="Test", mcq_count=2, long_answer_count=1)
    test_db.add(run)
    test_db.commit()

    response = client.get(f"/runs/{run.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["topic"] == "Test"
    assert data["id"] == run.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_api_runs.py -v`
Expected: Both tests fail with 404 (route not registered).

- [ ] **Step 3: Create `backend/api/__init__.py`**

```python
```
(Empty)

- [ ] **Step 4: Create `backend/api/runs.py`**

```python
import asyncio
import json
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from backend.config import settings
from backend.database import get_db
from backend.models.run import Run, ControlSet
from backend.models.assessment import Assessment
from backend.schemas.run_schemas import RunCreate, RunResponse
from backend.workers.assessment_worker import run_assessment_pipeline

router = APIRouter(prefix="/runs", tags=["runs"])

_TERMINAL_STAGES = {"complete", "error"}


async def _stream_run_progress(run_id: int, total_assessments: int):
    async_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = async_redis.pubsub()
    await pubsub.subscribe(f"run:{run_id}:progress")

    terminal_count = 0

    yield {"data": json.dumps({"run_id": run_id, "type": "run_started"})}

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        data = json.loads(message["data"])
        yield {"data": json.dumps(data)}

        if data.get("stage") in _TERMINAL_STAGES:
            terminal_count += 1
            if terminal_count >= total_assessments:
                break

    await pubsub.unsubscribe(f"run:{run_id}:progress")
    await async_redis.aclose()


@router.post("")
async def create_run(run_data: RunCreate, db: Session = Depends(get_db)):
    run = Run(
        topic=run_data.topic,
        expectations=run_data.expectations,
        mcq_count=run_data.mcq_count,
        long_answer_count=run_data.long_answer_count,
    )
    db.add(run)
    db.flush()

    control_sets = []
    for cs_data in run_data.control_sets:
        cs = ControlSet(
            run_id=run.id,
            personality=cs_data.personality,
            prompt_length=cs_data.prompt_length,
            result_length=cs_data.result_length,
            action_word_count=cs_data.action_word_count,
        )
        db.add(cs)
        control_sets.append(cs)
    db.flush()

    assessments = []
    for framework in run_data.frameworks:
        for cs in control_sets:
            a = Assessment(
                run_id=run.id,
                framework=framework,
                control_set_id=cs.id,
                status="pending",
            )
            db.add(a)
            assessments.append(a)
    db.commit()

    for a in assessments:
        run_assessment_pipeline.delay(a.id)

    return EventSourceResponse(
        _stream_run_progress(run.id, len(assessments))
    )


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
```

- [ ] **Step 5: Register the router in `backend/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.runs import router as runs_router

app = FastAPI(title="Assessment Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router)

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Run the tests**

Run: `pytest backend/tests/test_api_runs.py -v`
Expected: Both tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/api/ backend/main.py
git commit -m "feat: add POST /runs (SSE stream) and GET /runs/{id} routes"
```

---

## Task 12: Assessments API

**Files:**
- Create: `backend/api/assessments.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_api_assessments.py`:

```python
from backend.models.run import Run, ControlSet
from backend.models.assessment import Assessment
from backend.models.question import Question, MCQOption, ModelAnswer

def _seed_assessment(test_db):
    run = Run(topic="TCP/IP", expectations="test", mcq_count=1, long_answer_count=1)
    test_db.add(run)
    test_db.commit()
    cs = ControlSet(run_id=run.id, personality="formal", prompt_length="medium", result_length="medium", action_word_count=2)
    test_db.add(cs)
    test_db.commit()
    a = Assessment(run_id=run.id, framework="forge", control_set_id=cs.id, status="complete")
    test_db.add(a)
    test_db.commit()

    q1 = Question(assessment_id=a.id, type="mcq", body="What is SYN?", order=0)
    test_db.add(q1)
    test_db.flush()
    test_db.add(MCQOption(question_id=q1.id, body="Synchronize", is_correct=True))
    test_db.add(MCQOption(question_id=q1.id, body="Signal", is_correct=False))
    test_db.add(MCQOption(question_id=q1.id, body="Send", is_correct=False))
    test_db.add(MCQOption(question_id=q1.id, body="System", is_correct=False))

    q2 = Question(assessment_id=a.id, type="long_answer", body="Explain congestion control.", order=1)
    test_db.add(q2)
    test_db.flush()
    test_db.add(ModelAnswer(question_id=q2.id, body="TCP uses slow start..."))
    test_db.commit()
    return a

def test_get_assessment(client, test_db):
    a = _seed_assessment(test_db)
    response = client.get(f"/assessments/{a.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == a.id
    assert data["framework"] == "forge"
    assert len(data["questions"]) == 2
    assert data["questions"][0]["type"] == "mcq"
    assert len(data["questions"][0]["options"]) == 4

def test_get_assessment_not_found(client):
    response = client.get("/assessments/999")
    assert response.status_code == 404

def test_regenerate_assessment(client, test_db):
    from unittest.mock import patch
    a = _seed_assessment(test_db)
    with patch("backend.api.assessments.run_assessment_pipeline") as mock_task:
        mock_task.delay = lambda x: None
        response = client.post(f"/assessments/{a.id}/regenerate")
    assert response.status_code == 200
    data = response.json()
    assert data["assessment_id"] == a.id
    assert data["status"] == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_api_assessments.py -v`
Expected: All tests fail with 404.

- [ ] **Step 3: Create response schema for assessment detail**

Add to `backend/schemas/run_schemas.py`:

```python
class MCQOptionDetail(BaseModel):
    id: int
    body: str
    is_correct: bool
    model_config = {"from_attributes": True}

class ModelAnswerDetail(BaseModel):
    body: str
    model_config = {"from_attributes": True}

class QuestionDetail(BaseModel):
    id: int
    type: str
    body: str
    order: int
    options: list[MCQOptionDetail]
    model_answer: ModelAnswerDetail | None
    model_config = {"from_attributes": True}

class AssessmentDetailResponse(BaseModel):
    id: int
    framework: str
    control_set_id: int
    status: str
    questions: list[QuestionDetail]
    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Create `backend/api/assessments.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.assessment import Assessment
from backend.schemas.run_schemas import AssessmentDetailResponse
from backend.workers.assessment_worker import run_assessment_pipeline

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.get("/{assessment_id}", response_model=AssessmentDetailResponse)
def get_assessment(assessment_id: int, db: Session = Depends(get_db)):
    a = db.get(Assessment, assessment_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return a


@router.post("/{assessment_id}/regenerate")
def regenerate_assessment(assessment_id: int, db: Session = Depends(get_db)):
    a = db.get(Assessment, assessment_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Clear old pipeline records
    if a.prompt_generation:
        db.delete(a.prompt_generation)
    if a.planner_output:
        db.delete(a.planner_output)
    if a.assessment_generation:
        db.delete(a.assessment_generation)
    for q in a.questions:
        db.delete(q)
    db.commit()

    a.status = "pending"
    db.commit()

    run_assessment_pipeline.delay(assessment_id)
    return {"assessment_id": assessment_id, "status": "pending"}
```

- [ ] **Step 5: Register the assessments router in `backend/main.py`**

```python
from backend.api.assessments import router as assessments_router
app.include_router(assessments_router)
```

- [ ] **Step 6: Run the tests**

Run: `pytest backend/tests/test_api_assessments.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/api/assessments.py backend/main.py backend/schemas/run_schemas.py
git commit -m "feat: add GET /assessments/{id} and POST /assessments/{id}/regenerate routes"
```

---

## Task 13: PDF Export

**Files:**
- Create: `backend/templates/pdf/student.html`
- Create: `backend/templates/pdf/answer_key.html`
- Modify: `backend/api/assessments.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api_assessments.py`:

```python
def test_export_pdf_student(client, test_db):
    a = _seed_assessment(test_db)
    response = client.post(f"/assessments/{a.id}/export-pdf?variant=student")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"

def test_export_pdf_answer_key(client, test_db):
    a = _seed_assessment(test_db)
    response = client.post(f"/assessments/{a.id}/export-pdf?variant=answer_key")
    assert response.status_code == 200
    assert response.content[:4] == b"%PDF"

def test_export_pdf_invalid_variant(client, test_db):
    a = _seed_assessment(test_db)
    response = client.post(f"/assessments/{a.id}/export-pdf?variant=invalid")
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_api_assessments.py::test_export_pdf_student -v`
Expected: 404 (route doesn't exist).

- [ ] **Step 3: Create `backend/templates/pdf/student.html`**

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; margin: 40px; font-size: 12pt; }
  h1 { font-size: 16pt; }
  .meta { color: #555; font-size: 10pt; margin-bottom: 24px; }
  .question { margin-bottom: 24px; }
  .question-label { font-weight: bold; }
  .options { margin-left: 24px; margin-top: 8px; }
  .option { margin-bottom: 6px; }
  .long-answer-box { border: 1px solid #ccc; min-height: 80px; margin-top: 10px; }
</style>
</head>
<body>
<h1>{{ topic }}</h1>
<div class="meta">Framework: {{ framework }} | Control Set: {{ control_summary }}</div>

{% for question in questions %}
<div class="question">
  <div class="question-label">Q{{ loop.index }}. [{{ question.type | upper }}] {{ question.body }}</div>
  {% if question.type == "mcq" %}
  <div class="options">
    {% for option in question.options %}
    <div class="option">○ {{ option.body }}</div>
    {% endfor %}
  </div>
  {% else %}
  <div class="long-answer-box"></div>
  <div style="font-size:10pt; color:#777; margin-top:4px;">Word guide: ~{{ answer_word_guide }}</div>
  {% endif %}
</div>
{% endfor %}
</body>
</html>
```

- [ ] **Step 4: Create `backend/templates/pdf/answer_key.html`**

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; margin: 40px; font-size: 12pt; }
  h1 { font-size: 16pt; }
  .meta { color: #555; font-size: 10pt; margin-bottom: 24px; }
  .question { margin-bottom: 24px; }
  .question-label { font-weight: bold; }
  .options { margin-left: 24px; margin-top: 8px; }
  .option { margin-bottom: 6px; }
  .correct { font-weight: bold; color: #1a7a3c; }
  .model-answer { background: #f5f5f5; padding: 10px; margin-top: 8px; font-size: 11pt; }
  .answer-key-badge { background: #c00; color: white; padding: 2px 8px; font-size: 10pt; border-radius: 3px; }
</style>
</head>
<body>
<h1>{{ topic }} <span class="answer-key-badge">ANSWER KEY</span></h1>
<div class="meta">Framework: {{ framework }} | Control Set: {{ control_summary }}</div>

{% for question in questions %}
<div class="question">
  <div class="question-label">Q{{ loop.index }}. [{{ question.type | upper }}] {{ question.body }}</div>
  {% if question.type == "mcq" %}
  <div class="options">
    {% for option in question.options %}
    <div class="option {% if option.is_correct %}correct{% endif %}">
      {% if option.is_correct %}✓{% else %}○{% endif %} {{ option.body }}
    </div>
    {% endfor %}
  </div>
  {% else %}
  {% if question.model_answer %}
  <div class="model-answer">{{ question.model_answer.body }}</div>
  {% endif %}
  {% endif %}
</div>
{% endfor %}
</body>
</html>
```

- [ ] **Step 5: Add the export-pdf endpoint to `backend/api/assessments.py`**

Add these imports at top:
```python
import os
from typing import Literal
from fastapi.responses import Response
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
```

Add this route:

```python
_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "pdf")
_jinja_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR))


@router.post("/{assessment_id}/export-pdf")
def export_pdf(
    assessment_id: int,
    variant: Literal["student", "answer_key"],
    db: Session = Depends(get_db),
):
    a = db.get(Assessment, assessment_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    run = a.run
    cs = a.control_set
    control_summary = f"{cs.personality} / {cs.prompt_length} / {cs.action_word_count} words"
    answer_word_guide = {"short": "~100", "medium": "~200", "long": "~350"}.get(cs.result_length, "~200")

    template_name = "student.html" if variant == "student" else "answer_key.html"
    template = _jinja_env.get_template(template_name)

    questions_data = []
    for q in sorted(a.questions, key=lambda x: x.order):
        qd = {
            "type": q.type,
            "body": q.body,
            "options": [{"body": o.body, "is_correct": o.is_correct} for o in q.options],
            "model_answer": q.model_answer,
        }
        questions_data.append(qd)

    html_content = template.render(
        topic=run.topic,
        framework=a.framework.upper(),
        control_summary=control_summary,
        questions=questions_data,
        answer_word_guide=answer_word_guide,
    )

    pdf_bytes = HTML(string=html_content).write_pdf()
    filename = f"{run.topic.replace(' ', '-').lower()}-{a.framework}-cs{cs.id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

Add `jinja2` to `requirements.txt`:
```
jinja2==3.1.4
```

- [ ] **Step 6: Run the tests**

Run: `pytest backend/tests/test_api_assessments.py -v`
Expected: All tests PASS, including the 3 PDF export tests.

- [ ] **Step 7: Run all backend tests**

Run: `pytest backend/tests/ -v`
Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/templates/ backend/api/assessments.py backend/requirements.txt
git commit -m "feat: add PDF export endpoint with WeasyPrint for student and answer key variants"
```

---

## Task 14: Create all tables on startup

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add table creation on startup to `backend/main.py`**

```python
from backend.database import Base, engine
import backend.models.run  # noqa: F401
import backend.models.assessment  # noqa: F401
import backend.models.question  # noqa: F401

@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 2: Start the development server and verify it runs**

Run: `uvicorn backend.main:app --reload`
Expected: Server starts, no errors, `/health` returns `{"status": "ok"}`.

- [ ] **Step 3: Start Redis and a Celery worker (in separate terminals)**

```bash
# Terminal 1 - Redis (if not running via Docker)
redis-server

# Terminal 2 - Celery worker
celery -A backend.celery_app worker --loglevel=info
```

Expected: Celery connects to Redis, reports "ready".

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat: auto-create database tables on FastAPI startup"
```
