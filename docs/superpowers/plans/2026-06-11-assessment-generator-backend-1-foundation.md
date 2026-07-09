# Assessment Generator — Backend Plan 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the FastAPI + SQLAlchemy + Celery project structure, create all ORM models, and define all Pydantic schemas used across the entire backend.

**Architecture:** FastAPI app with SQLAlchemy 2.x ORM backed by SQLite. All database models and Pydantic validation shapes are defined here so downstream plans (LLM pipeline and API) can import them without circular dependencies. No business logic in this plan — only infrastructure.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, Pydantic 2.x, pydantic-settings, pytest

> **RISEN Discrepancy:** The spec defines RISEN sections as `<role>`, `<instructions>`, `<step>`, `<end_goal>`, `<narrowing>`. Your RISEN skill uses Role, Instruction, Structure, Examples, Nuance — a different variant of the acronym. Downstream plans implement the **spec's definition**.

---

## File Map

| File | Responsibility |
|---|---|
| `backend/requirements.txt` | All Python dependencies pinned |
| `backend/config.py` | Settings from env vars (API key, Redis URL, SQLite path, LLM model) |
| `backend/database.py` | SQLAlchemy engine, session factory, `get_db` dependency |
| `backend/main.py` | FastAPI app, CORS, health endpoint |
| `backend/models/__init__.py` | Empty package marker |
| `backend/models/run.py` | `Run`, `ControlSet` ORM models |
| `backend/models/assessment.py` | `Assessment`, `PromptGeneration`, `PlannerOutput`, `AssessmentGeneration` ORM models |
| `backend/models/question.py` | `Question`, `MCQOption`, `ModelAnswer` ORM models |
| `backend/schemas/__init__.py` | Empty package marker |
| `backend/schemas/run_schemas.py` | Pydantic shapes for run create/response and assessment detail |
| `backend/schemas/prompt_schema.py` | Pydantic shape for Call 1 output |
| `backend/schemas/planner_schema.py` | Pydantic shapes for Call 2 output (plan + question plans) |
| `backend/schemas/assessment_schema.py` | Pydantic shapes for Call 3 output |
| `backend/tests/conftest.py` | pytest fixtures: in-memory SQLite DB, TestClient |

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
jinja2==3.1.4
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
from backend.models.question import Question  # noqa: F401

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

- [ ] **Step 7: Update `conftest.py` to import all models**

Add to the top of `backend/tests/conftest.py` so `Base.metadata.create_all` picks them up:

```python
import backend.models.run  # noqa: F401
import backend.models.assessment  # noqa: F401
import backend.models.question  # noqa: F401
```

Also add to `backend/models/run.py` at the top:

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

- [ ] **Step 8: Run the tests**

Run: `pytest backend/tests/test_schemas.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 9: Run all tests to confirm nothing regressed**

Run: `pytest backend/tests/ -v`
Expected: All tests PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/schemas/
git commit -m "feat: add Pydantic schemas for LLM I/O validation and API request/response shapes"
```
