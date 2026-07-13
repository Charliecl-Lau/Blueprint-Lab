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

### Task 2: Add Experiment Domain Models

**What this task is:** Task 2 changes the backend database vocabulary from production assessment generation to research experimentation. It introduces the persistent objects Blueprint Lab is built around: an `Experiment` contains one or more `Condition` records, each `Condition` can produce a `Generation`, and each `Generation` keeps its prompt, generated JSON, Word artifact, model metadata, and future rubric results. This is the foundation for reproducibility because every output is tied to the exact condition that produced it.

**Files:**
- Create: `backend/models/experiment.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_experiment_models.py`

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/test_experiment_models.py`:

```python
from backend.models.experiment import (
    Condition,
    DocumentArtifact,
    Experiment,
    Generation,
    PromptRecord,
    RubricResult,
)


def test_experiment_condition_generation_metadata_round_trip(test_db):
    experiment = Experiment(
        course="ENGR 101",
        topic="Free-body diagrams",
        learning_objectives="Apply equilibrium equations to planar systems.",
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=3,
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
        status="complete",
        model_name="gemini",
        model_version="gemini-2.0-flash",
        generation_time_ms=1200,
        generated_json={"questions": []},
    )
    test_db.add(generation)
    test_db.flush()

    prompt = PromptRecord(
        generation_id=generation.id,
        prompt_structure="openai",
        full_prompt="Generate an assessment.",
    )
    artifact = DocumentArtifact(
        generation_id=generation.id,
        filename="assessment.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        content=b"docx-bytes",
    )
    rubric = RubricResult(
        generation_id=generation.id,
        reviewer="Reviewer A",
        rubric_score=4.5,
        comments="Strong alignment.",
    )
    test_db.add_all([prompt, artifact, rubric])
    test_db.commit()

    saved = test_db.get(Generation, generation.id)
    assert saved.condition.condition_label == "CourseBridge=ON; FewShot=OFF; Documents=ON"
    assert saved.prompt_record.full_prompt == "Generate an assessment."
    assert saved.document_artifact.filename == "assessment.docx"
    assert saved.rubric_results[0].rubric_score == 4.5
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
pytest backend/tests/test_experiment_models.py -v
```

Expected: FAIL because `backend.models.experiment` does not exist.

- [ ] **Step 3: Implement the models**

Create `backend/models/experiment.py`:

```python
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, LargeBinary, String, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course: Mapped[str] = mapped_column(String, nullable=False)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    learning_objectives: Mapped[str] = mapped_column(String, nullable=False)
    assessment_type: Mapped[str] = mapped_column(String, nullable=False)
    difficulty: Mapped[str] = mapped_column(String, nullable=False)
    number_of_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    conditions: Mapped[list["Condition"]] = relationship("Condition", back_populates="experiment")
    generations: Mapped[list["Generation"]] = relationship("Generation", back_populates="experiment")


class Condition(Base):
    __tablename__ = "conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[int] = mapped_column(Integer, ForeignKey("experiments.id"), nullable=False)
    prompt_structure: Mapped[str] = mapped_column(String, nullable=False)
    course_bridge_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    few_shot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    documents_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    condition_label: Mapped[str] = mapped_column(String, nullable=False)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="conditions")
    generations: Mapped[list["Generation"]] = relationship("Generation", back_populates="condition")


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[int] = mapped_column(Integer, ForeignKey("experiments.id"), nullable=False)
    condition_id: Mapped[int] = mapped_column(Integer, ForeignKey("conditions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    model_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    generation_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    generated_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="generations")
    condition: Mapped["Condition"] = relationship("Condition", back_populates="generations")
    prompt_record: Mapped["PromptRecord"] = relationship("PromptRecord", back_populates="generation", uselist=False)
    document_artifact: Mapped["DocumentArtifact"] = relationship("DocumentArtifact", back_populates="generation", uselist=False)
    rubric_results: Mapped[list["RubricResult"]] = relationship("RubricResult", back_populates="generation")


class PromptRecord(Base):
    __tablename__ = "prompt_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generation_id: Mapped[int] = mapped_column(Integer, ForeignKey("generations.id"), nullable=False)
    prompt_structure: Mapped[str] = mapped_column(String, nullable=False)
    full_prompt: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    generation: Mapped["Generation"] = relationship("Generation", back_populates="prompt_record")


class DocumentArtifact(Base):
    __tablename__ = "document_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generation_id: Mapped[int] = mapped_column(Integer, ForeignKey("generations.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    generation: Mapped["Generation"] = relationship("Generation", back_populates="document_artifact")


class RubricResult(Base):
    __tablename__ = "rubric_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generation_id: Mapped[int] = mapped_column(Integer, ForeignKey("generations.id"), nullable=False)
    reviewer: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rubric_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    comments: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    generation: Mapped["Generation"] = relationship("Generation", back_populates="rubric_results")
```

- [ ] **Step 4: Register the models**

Modify `backend/main.py` imports:

```python
import backend.models.experiment  # noqa: F401
```

- [ ] **Step 5: Run model tests**

Run:

```powershell
pytest backend/tests/test_experiment_models.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/models/experiment.py backend/main.py backend/tests/test_experiment_models.py
git commit -m "refactor: add Blueprint Lab experiment models" -m "This introduces the research-domain records for experiments, conditions, generations, prompts, document artifacts, and rubric results. The new schema makes each generated assessment traceable to an explicit experimental condition and leaves room for later manual or automated rubric scoring."
```

---

### Task 3: Replace Planner-Based Schemas With Experiment Schemas

**What this task is:** Task 3 defines the request and response contracts that the API and frontend will use for Blueprint Lab. The old schemas describe production runs, control sets, prompt frameworks, and planner output; the new schemas describe research inputs, fixed prompt structures, factor toggles, conditions, and generations. This task does not run the LLM yet. It makes the public data shape match the experiment architecture created in Task 2.

**Files:**
- Create: `backend/schemas/experiment_schema.py`
- Test: `backend/tests/test_experiment_schemas.py`

- [ ] **Step 1: Write the failing schema tests**

Create `backend/tests/test_experiment_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from backend.schemas.experiment_schema import ExperimentCreate, PromptFactors


def test_experiment_create_defaults_to_openai_and_all_factors_off():
    payload = ExperimentCreate(
        course="ENGR 101",
        topic="Statics",
        learning_objectives="Solve equilibrium problems.",
        assessment_type="mixed",
        difficulty="introductory",
        number_of_questions=4,
    )

    assert payload.prompt_structure == "openai"
    assert payload.factors == PromptFactors()
    assert payload.factors.course_bridge is False
    assert payload.factors.few_shot is False
    assert payload.factors.documents is False


def test_experiment_create_accepts_anthropic_prompt_structure():
    payload = ExperimentCreate(
        course="ENGR 201",
        topic="Signals",
        learning_objectives="Analyze simple signals.",
        assessment_type="short_answer",
        difficulty="intermediate",
        number_of_questions=2,
        prompt_structure="anthropic",
        factors={"course_bridge": True, "few_shot": True, "documents": False},
    )

    assert payload.prompt_structure == "anthropic"
    assert payload.factors.course_bridge is True


def test_experiment_create_rejects_removed_frameworks():
    with pytest.raises(ValidationError):
        ExperimentCreate(
            course="ENGR 101",
            topic="Statics",
            learning_objectives="Solve equilibrium problems.",
            assessment_type="mixed",
            difficulty="introductory",
            number_of_questions=4,
            prompt_structure="forge",
        )
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
pytest backend/tests/test_experiment_schemas.py -v
```

Expected: FAIL because the schema module does not exist.

- [ ] **Step 3: Implement schemas**

Create `backend/schemas/experiment_schema.py`:

```python
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


PromptStructure = Literal["openai", "anthropic"]
AssessmentType = Literal["mcq", "short_answer", "mixed"]


class PromptFactors(BaseModel):
    course_bridge: bool = False
    few_shot: bool = False
    documents: bool = False


class ExperimentCreate(BaseModel):
    course: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    learning_objectives: str = Field(min_length=1)
    assessment_type: AssessmentType = "mixed"
    difficulty: str = Field(min_length=1)
    number_of_questions: int = Field(default=4, ge=1, le=50)
    prompt_structure: PromptStructure = "openai"
    factors: PromptFactors = Field(default_factory=PromptFactors)


class ConditionResponse(BaseModel):
    id: int
    prompt_structure: PromptStructure
    course_bridge_enabled: bool
    few_shot_enabled: bool
    documents_enabled: bool
    condition_label: str

    model_config = {"from_attributes": True}


class GenerationSummary(BaseModel):
    id: int
    condition_id: int
    status: str
    model_name: Optional[str]
    model_version: Optional[str]
    generation_time_ms: Optional[int]

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ExperimentResponse(BaseModel):
    id: int
    course: str
    topic: str
    learning_objectives: str
    assessment_type: str
    difficulty: str
    number_of_questions: int
    created_at: datetime
    conditions: list[ConditionResponse]
    generations: list[GenerationSummary]

    model_config = {"from_attributes": True}


class GenerationDetailResponse(GenerationSummary):
    generated_json: Optional[dict]
    condition: ConditionResponse
    prompt_text: Optional[str] = None
```

- [ ] **Step 4: Run schema tests**

Run:

```powershell
pytest backend/tests/test_experiment_schemas.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/schemas/experiment_schema.py backend/tests/test_experiment_schemas.py
git commit -m "refactor: define research experiment schemas" -m "This replaces production prompt-framework request shapes with research-oriented experiment inputs. The schema fixes OpenAI as the default prompt structure, permits Anthropic as the only optional structure, and exposes prompt design factors as independent booleans."
```

---