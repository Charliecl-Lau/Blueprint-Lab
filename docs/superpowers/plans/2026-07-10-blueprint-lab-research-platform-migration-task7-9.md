# Blueprint Lab Research Platform Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fork Blueprint into Blueprint Lab, a controlled research platform where users run experiment conditions that generate reproducible engineering assessments with complete prompt, factor, model, document, and evaluation metadata.

**Architecture:** Replace the current `Run -> ControlSet -> Assessment` workflow with `Experiment -> Condition -> Generation -> Evaluation`, while preserving FastAPI, React, Celery, Redis progress events, database persistence, regeneration, and export behavior. Remove the planner stage entirely so the LLM path is prompt generation, question generation, DOCX generation, metadata logging, and persistence.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Celery, Redis/SSE, React, TypeScript, Vite, Zustand, `python-docx`, pytest, Vitest.

---

## File Structure

- Rename conceptually, not necessarily by folder name in the first commit: keep `backend/` and `frontend/` stable to reduce churn.
- Create `backend/models/experiment.py` for `Experiment`, `Condition`, `Generation`, `RubricResult`, `PromptRecord`, and `DocumentArtifact`.
- Create `backend/schemas/experiment_schema.py` for request/response DTOs.
- Create `backend/services/prompt_factors.py` for fixed prompt structures and independently toggled prompt design factors.
- Modify `backend/services/prompt_generator.py` so it accepts research inputs and factor toggles instead of production controls.
- Modify `backend/services/generator.py` so it generates questions directly from the generated prompt.
- Delete `backend/services/planner.py`, `backend/services/validator.py`, `backend/schemas/planner_schema.py`, and their tests after replacement tests pass.
- Create `backend/services/docx_exporter.py` to generate instructor-ready Word documents.
- Replace `backend/workers/assessment_worker.py` with an experiment generation worker.
- Replace `backend/api/runs.py` with `backend/api/experiments.py`; keep a temporary compatibility import only if needed during transition.
- Modify `backend/api/assessments.py` to use generation IDs and DOCX export as the primary export.
- Modify `backend/main.py` to expose `Blueprint Lab` and register experiment routes/models.
- Modify frontend types, API clients, pages, and store from run/assessment language to experiment/condition/generation language.
- Modify `README.md` to describe Blueprint Lab and the research workflow.

---

## Prerequisite Fork Plan

Task 1 is now its own setup plan: `docs/superpowers/plans/2026-07-09-blueprint-lab-forking.md`.

Execute that plan before starting this migration. This migration plan assumes all source edits happen in the standalone Blueprint Lab repository at `C:\Users\yeekw\Documents\Blueprint-Lab`, with its own `origin` remote and the original Blueprint repository kept only as optional `upstream` lineage.

---

### Task 7: Replace the Worker Pipeline

**Files:**
- Modify: `backend/workers/assessment_worker.py`
- Test: `backend/tests/test_worker.py`

- [ ] **Step 1: Write worker tests for the new pipeline**

Replace planner validation tests in `backend/tests/test_worker.py` with:

```python
from unittest.mock import MagicMock, patch

import pytest

from backend.models.experiment import Condition, Experiment, Generation


@pytest.fixture
def generation_fixture(test_db):
    experiment = Experiment(
        course="ENGR 101",
        topic="Statics",
        learning_objectives="Solve equilibrium problems.",
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=2,
    )
    test_db.add(experiment)
    test_db.flush()
    condition = Condition(
        experiment_id=experiment.id,
        prompt_structure="openai",
        course_bridge_enabled=True,
        few_shot_enabled=False,
        documents_enabled=True,
        condition_label="CourseBridge=ON; FewShot=OFF; Documents=ON",
    )
    test_db.add(condition)
    test_db.flush()
    generation = Generation(
        experiment_id=experiment.id,
        condition_id=condition.id,
        status="pending",
    )
    test_db.add(generation)
    test_db.commit()
    return generation


def test_generation_pipeline_logs_prompt_json_docx_and_metadata(generation_fixture, test_db):
    with patch("backend.workers.assessment_worker.LLMClient") as MockLLM, \
         patch("backend.workers.assessment_worker.SessionLocal") as MockSession, \
         patch("backend.workers.assessment_worker.redis_client") as mock_redis:
        MockSession.return_value = test_db
        test_db.close = MagicMock()
        llm = MagicMock()
        llm.model_name = "gemini"
        llm.model_version = "gemini-2.0-flash"
        llm.generate_json.return_value = {
            "questions": [
                {
                    "type": "long_answer",
                    "body": "Explain equilibrium.",
                    "options": [],
                    "model_answer": "Net force and net moment are zero.",
                }
            ]
        }
        MockLLM.return_value = llm

        from backend.workers.assessment_worker import run_generation_pipeline
        run_generation_pipeline(generation_fixture.id)

        test_db.refresh(generation_fixture)
        assert generation_fixture.status == "complete"
        assert generation_fixture.generated_json["questions"][0]["body"] == "Explain equilibrium."
        assert generation_fixture.prompt_record.full_prompt
        assert generation_fixture.document_artifact.content.startswith(b"PK")
        assert generation_fixture.model_name == "gemini"
        assert generation_fixture.generation_time_ms is not None
        assert mock_redis.publish.called
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
pytest backend/tests/test_worker.py -v
```

Expected: FAIL because `run_generation_pipeline` does not exist.

- [ ] **Step 3: Implement the worker**

Modify `backend/workers/assessment_worker.py` to remove planner imports and expose `run_generation_pipeline`. Preserve the filename for minimal Celery configuration churn:

```python
import json
import time

import redis
from sqlalchemy.orm import Session

from backend.celery_app import celery_app
from backend.config import settings
from backend.database import SessionLocal
from backend.models.experiment import DocumentArtifact, Generation, PromptRecord, utc_now
from backend.schemas.experiment_schema import PromptFactors
from backend.services.docx_exporter import build_assessment_docx
from backend.services.generator import generate_questions
from backend.services.llm_client import LLMClient
from backend.services.prompt_generator import generate_prompt


redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _publish_progress(experiment_id: int, generation_id: int, condition_id: int, stage: str):
    redis_client.publish(
        f"experiment:{experiment_id}:progress",
        json.dumps({
            "generation_id": generation_id,
            "condition_id": condition_id,
            "stage": stage,
        }),
    )


def _set_status(db: Session, generation: Generation, status: str):
    generation.status = status
    db.commit()


def _factors_from_condition(condition) -> PromptFactors:
    return PromptFactors(
        course_bridge=condition.course_bridge_enabled,
        few_shot=condition.few_shot_enabled,
        documents=condition.documents_enabled,
    )


@celery_app.task(bind=True, max_retries=3)
def run_generation_pipeline(self, generation_id: int):
    db = SessionLocal()
    try:
        generation = db.get(Generation, generation_id)
        if generation is None:
            return

        experiment = generation.experiment
        condition = generation.condition

        try:
            llm = LLMClient()
            started = time.perf_counter()

            _set_status(db, generation, "prompting")
            _publish_progress(experiment.id, generation.id, condition.id, "prompting")
            prompt_text = generate_prompt(
                course=experiment.course,
                topic=experiment.topic,
                learning_objectives=experiment.learning_objectives,
                assessment_type=experiment.assessment_type,
                difficulty=experiment.difficulty,
                number_of_questions=experiment.number_of_questions,
                prompt_structure=condition.prompt_structure,
                factors=_factors_from_condition(condition),
            )
            prompt_record = PromptRecord(
                generation_id=generation.id,
                prompt_structure=condition.prompt_structure,
                full_prompt=prompt_text,
            )
            db.add(prompt_record)
            db.commit()
            db.refresh(prompt_record)

            _set_status(db, generation, "generating")
            _publish_progress(experiment.id, generation.id, condition.id, "generating")
            generated = generate_questions(llm=llm, generated_prompt=prompt_text)
            generation.generated_json = generated.model_dump()
            generation.model_name = getattr(llm, "model_name", None)
            generation.model_version = getattr(llm, "model_version", None)
            generation.generation_time_ms = int((time.perf_counter() - started) * 1000)
            generation.completed_at = utc_now()
            db.commit()

            _set_status(db, generation, "documenting")
            _publish_progress(experiment.id, generation.id, condition.id, "documenting")
            docx_bytes = build_assessment_docx(
                assessment_id=generation.id,
                prompt_id=prompt_record.id,
                condition_label=condition.condition_label,
                course=experiment.course,
                topic=experiment.topic,
                questions=generation.generated_json["questions"],
            )
            db.add(DocumentArtifact(
                generation_id=generation.id,
                filename=f"blueprint-lab-generation-{generation.id}.docx",
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                content=docx_bytes,
            ))
            db.commit()

            _set_status(db, generation, "complete")
            _publish_progress(experiment.id, generation.id, condition.id, "complete")
        except Exception as exc:
            _set_status(db, generation, "error")
            _publish_progress(experiment.id, generation.id, condition.id, "error")
            raise self.retry(exc=exc, countdown=10)
    finally:
        db.close()
```

- [ ] **Step 4: Run worker tests**

Run:

```powershell
pytest backend/tests/test_worker.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/workers/assessment_worker.py backend/tests/test_worker.py
git commit -m "refactor: replace planner pipeline with generation pipeline" -m "This changes the asynchronous worker to run the Blueprint Lab research pipeline: prompt generation, question generation, Word document generation, metadata logging, and persistence. Planner generation and validation are removed from the runtime path to reduce experimental variability."
```

---

### Task 8: Add Experiment API and Progress Streaming

**Files:**
- Create: `backend/api/experiments.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_api_experiments.py`

- [ ] **Step 1: Write API tests**

Create `backend/tests/test_api_experiments.py`:

```python
from unittest.mock import patch


def test_create_experiment_creates_condition_and_generation(client):
    with patch("backend.api.experiments.run_generation_pipeline.delay") as delay:
        response = client.post("/experiments", json={
            "course": "ENGR 101",
            "topic": "Statics",
            "learning_objectives": "Solve equilibrium problems.",
            "assessment_type": "mixed",
            "difficulty": "introductory",
            "number_of_questions": 2,
            "prompt_structure": "openai",
            "factors": {
                "course_bridge": True,
                "few_shot": False,
                "documents": True,
            },
        })

    assert response.status_code == 200
    data = response.json()
    assert data["course"] == "ENGR 101"
    assert data["conditions"][0]["condition_label"] == "CourseBridge=ON; FewShot=OFF; Documents=ON"
    assert data["generations"][0]["status"] == "pending"
    delay.assert_called_once()


def test_get_experiment_returns_generations(client):
    with patch("backend.api.experiments.run_generation_pipeline.delay"):
        created = client.post("/experiments", json={
            "course": "ENGR 101",
            "topic": "Statics",
            "learning_objectives": "Solve equilibrium problems.",
            "assessment_type": "mixed",
            "difficulty": "introductory",
            "number_of_questions": 2,
        }).json()

    response = client.get(f"/experiments/{created['id']}")

    assert response.status_code == 200
    assert len(response.json()["generations"]) == 1
```

- [ ] **Step 2: Run failing API tests**

Run:

```powershell
pytest backend/tests/test_api_experiments.py -v
```

Expected: FAIL because the route does not exist.

- [ ] **Step 3: Implement experiment route**

Create `backend/api/experiments.py`:

```python
import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from backend.config import settings
from backend.database import get_db
from backend.models.experiment import Condition, Experiment, Generation
from backend.schemas.experiment_schema import ExperimentCreate, ExperimentResponse
from backend.services.prompt_factors import build_condition_label
from backend.workers.assessment_worker import run_generation_pipeline


router = APIRouter(prefix="/experiments", tags=["experiments"])
_TERMINAL_STAGES = {"complete", "error"}


async def _stream_experiment_progress(experiment_id: int, total_generations: int):
    async_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = async_redis.pubsub()
    await pubsub.subscribe(f"experiment:{experiment_id}:progress")
    terminal_count = 0

    yield {"data": json.dumps({"experiment_id": experiment_id, "type": "experiment_started"})}

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        data = json.loads(message["data"])
        yield {"data": json.dumps(data)}
        if data.get("stage") in _TERMINAL_STAGES:
            terminal_count += 1
            if terminal_count >= total_generations:
                break

    await pubsub.unsubscribe(f"experiment:{experiment_id}:progress")
    await async_redis.aclose()


@router.post("", response_model=ExperimentResponse)
def create_experiment(payload: ExperimentCreate, db: Session = Depends(get_db)):
    experiment = Experiment(
        course=payload.course,
        topic=payload.topic,
        learning_objectives=payload.learning_objectives,
        assessment_type=payload.assessment_type,
        difficulty=payload.difficulty,
        number_of_questions=payload.number_of_questions,
    )
    db.add(experiment)
    db.flush()

    condition = Condition(
        experiment_id=experiment.id,
        prompt_structure=payload.prompt_structure,
        course_bridge_enabled=payload.factors.course_bridge,
        few_shot_enabled=payload.factors.few_shot,
        documents_enabled=payload.factors.documents,
        condition_label=build_condition_label(payload.factors),
    )
    db.add(condition)
    db.flush()

    generation = Generation(
        experiment_id=experiment.id,
        condition_id=condition.id,
        status="pending",
    )
    db.add(generation)
    db.commit()

    run_generation_pipeline.delay(generation.id)
    db.refresh(experiment)
    return experiment


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(experiment_id: int, db: Session = Depends(get_db)):
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment


@router.get("/{experiment_id}/progress")
async def experiment_progress(experiment_id: int, db: Session = Depends(get_db)):
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return EventSourceResponse(_stream_experiment_progress(experiment.id, len(experiment.generations)))
```

- [ ] **Step 4: Register route**

Modify `backend/main.py`:

```python
from backend.api.experiments import router as experiments_router

app = FastAPI(title="Blueprint Lab")
app.include_router(experiments_router)
```

Keep old run routes only until the frontend is migrated. Remove them in Task 12.

- [ ] **Step 5: Run API tests**

Run:

```powershell
pytest backend/tests/test_api_experiments.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/api/experiments.py backend/main.py backend/tests/test_api_experiments.py
git commit -m "feat: add experiment API" -m "This adds the Blueprint Lab API surface for creating and reading experiments, conditions, and generations. New generations are queued through the research pipeline and progress events are streamed by experiment rather than by production assessment run."
```

---

### Task 9: Add Generation Detail, Regeneration, and DOCX Export API

**Files:**
- Modify: `backend/api/assessments.py`
- Test: `backend/tests/test_api_generations.py`

- [ ] **Step 1: Write generation API tests**

Create `backend/tests/test_api_generations.py`:

```python
from backend.models.experiment import Condition, DocumentArtifact, Experiment, Generation, PromptRecord


def make_generation(test_db):
    experiment = Experiment(
        course="ENGR 101",
        topic="Statics",
        learning_objectives="Solve equilibrium problems.",
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=1,
    )
    test_db.add(experiment)
    test_db.flush()
    condition = Condition(
        experiment_id=experiment.id,
        prompt_structure="openai",
        course_bridge_enabled=False,
        few_shot_enabled=False,
        documents_enabled=False,
        condition_label="CourseBridge=OFF; FewShot=OFF; Documents=OFF",
    )
    test_db.add(condition)
    test_db.flush()
    generation = Generation(
        experiment_id=experiment.id,
        condition_id=condition.id,
        status="complete",
        generated_json={"questions": []},
    )
    test_db.add(generation)
    test_db.flush()
    test_db.add(PromptRecord(generation_id=generation.id, prompt_structure="openai", full_prompt="Prompt"))
    test_db.add(DocumentArtifact(
        generation_id=generation.id,
        filename="generation.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=b"docx-bytes",
    ))
    test_db.commit()
    return generation


def test_get_generation_detail(client, test_db):
    generation = make_generation(test_db)

    response = client.get(f"/generations/{generation.id}")

    assert response.status_code == 200
    assert response.json()["prompt_text"] == "Prompt"
    assert response.json()["condition"]["condition_label"] == "CourseBridge=OFF; FewShot=OFF; Documents=OFF"


def test_export_docx_returns_word_artifact(client, test_db):
    generation = make_generation(test_db)

    response = client.get(f"/generations/{generation.id}/export-docx")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert response.content == b"docx-bytes"
```

- [ ] **Step 2: Run failing generation API tests**

Run:

```powershell
pytest backend/tests/test_api_generations.py -v
```

Expected: FAIL because generation routes do not exist.

- [ ] **Step 3: Replace assessment routes with generation routes**

Modify `backend/api/assessments.py` or create `backend/api/generations.py`. Prefer creating `backend/api/generations.py` and registering it:

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.experiment import DocumentArtifact, Generation, PromptRecord
from backend.schemas.experiment_schema import GenerationDetailResponse
from backend.workers.assessment_worker import run_generation_pipeline


router = APIRouter(prefix="/generations", tags=["generations"])


@router.get("/{generation_id}", response_model=GenerationDetailResponse)
def get_generation(generation_id: int, db: Session = Depends(get_db)):
    generation = db.get(Generation, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    return GenerationDetailResponse(
        id=generation.id,
        condition_id=generation.condition_id,
        status=generation.status,
        model_name=generation.model_name,
        model_version=generation.model_version,
        generation_time_ms=generation.generation_time_ms,
        generated_json=generation.generated_json,
        condition=generation.condition,
        prompt_text=generation.prompt_record.full_prompt if generation.prompt_record else None,
    )


@router.post("/{generation_id}/regenerate")
def regenerate_generation(generation_id: int, db: Session = Depends(get_db)):
    generation = db.get(Generation, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Generation not found")

    if generation.prompt_record:
        db.delete(generation.prompt_record)
    if generation.document_artifact:
        db.delete(generation.document_artifact)
    generation.generated_json = None
    generation.generation_time_ms = None
    generation.completed_at = None
    generation.status = "pending"
    db.commit()

    run_generation_pipeline.delay(generation.id)
    return {"generation_id": generation.id, "status": "pending"}


@router.get("/{generation_id}/export-docx")
def export_docx(generation_id: int, db: Session = Depends(get_db)):
    artifact = db.query(DocumentArtifact).filter_by(generation_id=generation_id).first()
    if artifact is None:
        raise HTTPException(status_code=404, detail="DOCX artifact not found")
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )
```

- [ ] **Step 4: Register generation route**

Modify `backend/main.py`:

```python
from backend.api.generations import router as generations_router

app.include_router(generations_router)
```

- [ ] **Step 5: Run generation API tests**

Run:

```powershell
pytest backend/tests/test_api_generations.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/api/generations.py backend/main.py backend/tests/test_api_generations.py
git commit -m "feat: add generation detail and Word export API" -m "This exposes generated research artifacts by generation ID, supports regeneration without rerunning a full experiment, and makes DOCX the primary export endpoint. The API keeps each artifact linked to its condition, prompt, model metadata, and generated JSON."
```

