# Assessment Generator — Backend Plan 3: Worker, API & Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the LLM pipeline into a Celery task worker, expose the REST + SSE API, add PDF export, and create all database tables on startup — producing a fully runnable backend.

**Architecture:** Celery workers pull assessment tasks from a Redis queue, execute the 4-stage pipeline (prompt → plan → validate → generate), write DB records, and publish SSE progress events to a Redis pub/sub channel. FastAPI subscribes to that channel and streams events to the client over SSE. Two additional REST routes handle assessment retrieval, regeneration, and PDF export via WeasyPrint + Jinja2 templates.

**Tech Stack:** Python 3.11+, FastAPI, Celery 5.x, Redis, `sse-starlette`, `redis-py`, WeasyPrint, Jinja2, pytest

**Prerequisites:** Plans 1 and 2 must be complete. All imports from `backend.models`, `backend.schemas`, `backend.database`, and `backend.services` must resolve.

---

## File Map

| File | Responsibility |
|---|---|
| `backend/celery_app.py` | Celery app instance with Redis broker/backend |
| `backend/workers/__init__.py` | Empty package marker |
| `backend/workers/assessment_worker.py` | Celery task: chains all 4 stages, writes DB records, publishes SSE events |
| `backend/api/__init__.py` | Empty package marker |
| `backend/api/runs.py` | `POST /runs` (SSE stream) and `GET /runs/{id}` |
| `backend/api/assessments.py` | `GET /assessments/{id}`, `POST /assessments/{id}/regenerate`, `POST /assessments/{id}/export-pdf` |
| `backend/templates/pdf/student.html` | WeasyPrint template: questions only |
| `backend/templates/pdf/answer_key.html` | WeasyPrint template: questions + answers |
| `backend/main.py` | **Modified:** register routers, add startup table creation |

---

## Task 10: Celery App + Assessment Worker

**Files:**
- Create: `backend/celery_app.py`
- Create: `backend/workers/__init__.py`
- Create: `backend/workers/assessment_worker.py`

The worker executes all four stages for one assessment, writes records at each stage, publishes SSE progress events to Redis, and transitions `Assessment.status` at each stage.

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

        MockSession.return_value = test_db

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

        MockSession.return_value = test_db

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
    db = SessionLocal()
    try:
        assessment = db.get(Assessment, assessment_id)
        if assessment is None:
            return
        run = assessment.run
        control_set = assessment.control_set

        try:
            llm = LLMClient()

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

            _set_status(db, assessment, "planning")
            _publish_progress(run.id, assessment_id, assessment.framework, control_set.id, "planning")

            plan = generate_plan(llm=llm, generated_prompt=prompt_text)

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
    finally:
        db.close()
```

- [ ] **Step 6: Run the tests**

Run: `pytest backend/tests/test_worker.py -v`
Expected: Both tests PASS.

- [ ] **Step 7: Commit**

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

The `POST /runs` endpoint creates all DB records, enqueues 12 Celery tasks, then returns an `EventSourceResponse` that subscribes to the Redis pub/sub channel for that run and streams events until all 12 assessments reach a terminal state.

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

Replace the current contents of `backend/main.py` with:

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

- [ ] **Step 3: Create `backend/api/assessments.py`**

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

- [ ] **Step 4: Register the assessments router in `backend/main.py`**

```python
from backend.api.assessments import router as assessments_router
app.include_router(assessments_router)
```

- [ ] **Step 5: Run the tests**

Run: `pytest backend/tests/test_api_assessments.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/api/assessments.py backend/main.py
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

Add these imports at the top of `backend/api/assessments.py`:

```python
import os
from typing import Literal
from fastapi.responses import Response
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
```

Add these lines after the `router` declaration:

```python
_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "pdf")
_jinja_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR))
```

Add this route at the end of `backend/api/assessments.py`:

```python
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

- [ ] **Step 6: Run the tests**

Run: `pytest backend/tests/test_api_assessments.py -v`
Expected: All tests PASS, including the 3 PDF export tests.

- [ ] **Step 7: Commit**

```bash
git add backend/templates/ backend/api/assessments.py
git commit -m "feat: add PDF export endpoint with WeasyPrint for student and answer key variants"
```

---

## Task 14: Create Tables on Startup + Smoke Test

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add table creation on startup to `backend/main.py`**

Add these imports and event handler to `backend/main.py`:

```python
from backend.database import Base, engine
import backend.models.run  # noqa: F401
import backend.models.assessment  # noqa: F401
import backend.models.question  # noqa: F401

@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 2: Run all backend tests**

Run: `pytest backend/tests/ -v`
Expected: All tests PASS.

- [ ] **Step 3: Start the development server and verify it runs**

Run: `uvicorn backend.main:app --reload`
Expected: Server starts, no errors, `/health` returns `{"status": "ok"}`.

- [ ] **Step 4: Start Redis and a Celery worker (in separate terminals)**

```bash
# Terminal 1 - Redis (if not running via Docker)
redis-server

# Terminal 2 - Celery worker
celery -A backend.celery_app worker --loglevel=info
```

Expected: Celery connects to Redis, reports "ready".

- [ ] **Step 5: Commit**

```bash
git add backend/main.py
git commit -m "feat: auto-create database tables on FastAPI startup"
```
