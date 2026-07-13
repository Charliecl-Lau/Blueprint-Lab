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

### Task 4: Convert ChatGPT Web Instructions Into Research Prompt System

**What this task is:** Task 4 takes `prompt/chatgpt-system-prompt.md`, which was written for direct ChatGPT Web use, and turns it into an application system prompt suitable for Blueprint Lab. The adapted prompt keeps the MSE thermodynamics, traceability, concept-bridge, solution-quality, and Word-document requirements, but removes chat-only behaviors such as "provide a download link" and "prepend Blueprint Check". The backend will use this converted system prompt to generate structured assessment JSON that later feeds the DOCX exporter.

**Files:**
- Source reference: `prompt/chatgpt-system-prompt.md`
- Create: `backend/services/research_system_prompt.py`
- Create: `backend/services/prompt_factors.py`
- Modify: `backend/services/prompt_generator.py`
- Test: `backend/tests/test_research_system_prompt.py`
- Test: `backend/tests/test_prompt_factors.py`
- Test: `backend/tests/test_prompt_generator.py`

- [ ] **Step 1: Write system prompt conversion tests**

Create `backend/tests/test_research_system_prompt.py`:

```python
from backend.services.research_system_prompt import BLUEPRINT_LAB_SYSTEM_PROMPT


def test_converted_system_prompt_preserves_research_requirements():
    assert "undergraduate MSE thermodynamics assessment" in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "MSE202" in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "MSE302" in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "Concept-Map Bridge" in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "Assessment Quality Check" in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "Suggested Revision Options" in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "native Word equation" in BLUEPRINT_LAB_SYSTEM_PROMPT


def test_converted_system_prompt_removes_chatgpt_web_only_behavior():
    assert "download link" not in BLUEPRINT_LAB_SYSTEM_PROMPT.lower()
    assert "Blueprint Check" not in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "Do not provide only plain text in the chat" not in BLUEPRINT_LAB_SYSTEM_PROMPT
    assert "Return only valid JSON" in BLUEPRINT_LAB_SYSTEM_PROMPT
```

- [ ] **Step 2: Write factor tests**

Create `backend/tests/test_prompt_factors.py`:

```python
from backend.schemas.experiment_schema import PromptFactors
from backend.services.prompt_factors import build_condition_label, build_research_prompt


def test_condition_label_records_each_factor_state():
    label = build_condition_label(PromptFactors(course_bridge=True, few_shot=False, documents=True))

    assert label == "CourseBridge=ON; FewShot=OFF; Documents=ON"


def test_openai_prompt_structure_uses_converted_system_prompt_and_factor_sections():
    prompt = build_research_prompt(
        prompt_structure="openai",
        course="MSE302",
        topic="Gibbs free energy and phase equilibrium",
        learning_objectives="Connect chemical potential to phase stability.",
        assessment_type="mixed",
        difficulty="intermediate",
        number_of_questions=1,
        factors=PromptFactors(course_bridge=True, few_shot=False, documents=True),
    )

    assert "# Role" in prompt
    assert "# Goal" in prompt
    assert "MSE202" in prompt
    assert "MSE302" in prompt
    assert "Concept-Map Bridge" in prompt
    assert "Course Bridge" in prompt
    assert "Few-shot Examples" not in prompt
    assert "Instructor Examples / Attached Documents" in prompt
    assert "CourseBridge=ON; FewShot=OFF; Documents=ON" in prompt
    assert "Return only valid JSON" in prompt
    assert "download link" not in prompt.lower()
    assert "Blueprint Check" not in prompt


def test_anthropic_prompt_structure_is_available_but_fixed():
    prompt = build_research_prompt(
        prompt_structure="anthropic",
        course="MSE302",
        topic="Laplace transforms in heat-transfer modeling",
        learning_objectives="Apply mathematical tools to engineering thermodynamics reasoning.",
        assessment_type="short_answer",
        difficulty="intermediate",
        number_of_questions=1,
        factors=PromptFactors(),
    )

    assert "<role>" in prompt
    assert "<task>" in prompt
    assert "Prompt Structure: anthropic" in prompt
    assert "Return only valid JSON" in prompt
```

- [ ] **Step 3: Run the failing tests**

Run:

```powershell
pytest backend/tests/test_research_system_prompt.py backend/tests/test_prompt_factors.py -v
```

Expected: FAIL because `research_system_prompt.py` and `prompt_factors.py` do not exist.

- [ ] **Step 4: Implement the converted system prompt**

Create `backend/services/research_system_prompt.py`:

```python
BLUEPRINT_LAB_SYSTEM_PROMPT = """You are Blueprint Lab's controlled research assessment-generation engine.

Your role is to generate instructor-ready undergraduate MSE thermodynamics assessment content for reproducible prompt-engineering experiments. The content must connect concepts from MSE202 and MSE302, use professional undergraduate thermodynamics notation, and be suitable for later rendering into a Microsoft Word .docx assessment document by the application.

This is not ChatGPT Web. Do not provide file-transfer URLs, chat-only confirmations, markdown-only final answers, or instruction-adherence markers. The application will create the .docx artifact after you return structured JSON.

Core requirements:
- Generate the requested number of questions, unless the experiment explicitly asks for one question.
- Keep the question aligned with undergraduate Materials Science and Engineering thermodynamics.
- Do not assume graduate-level thermodynamics unless explicitly requested.
- Make the problem solvable using only provided information or standard undergraduate course knowledge.
- Make assumptions explicit in the solution.
- Do not skip reasoning, algebraic steps, variable definitions, units, or physical interpretation in the solution.
- Avoid vague, generic, or purely physics/chemistry-style contexts.
- Prioritize thermodynamic correctness, pedagogical alignment, clear notation, and instructor usability.

Every generated question object must support these document sections:
1. Assessment Metadata
2. Student-Facing Question
3. Fully Worked Solution
4. Assessment Quality Check
5. Suggested Revision Options

Assessment Metadata must include these fields when available:
- Prompt Template ID (PT-ID)
- Actual Prompt ID (AP-ID)
- Output ID (OUT-ID)
- Final Question ID
- Question Title
- Question Type
- Difficulty Level
- Intended Assessment Setting
- MSE202 Concept(s)
- MSE302 Concept(s)
- Concept-Map Bridge
- Materials Science Context
- Estimated Time for a Well-Prepared Student
- Learning Objective(s)
- ID Requirements

Never invent or modify traceability IDs. If an ID is not provided, use \"Not Assigned\".

The Concept-Map Bridge must explain how the selected MSE202 and MSE302 concepts are connected. The Materials Science Context must explain why the assessment is relevant to Materials Science and Engineering.

Student-facing questions must be clear, self-contained, unambiguous, and include all data needed to solve the problem. They must use undergraduate MSE thermodynamics notation, include a materials science motivation or scenario, state allowed assumptions, and avoid unnecessary complexity unless requested.

Fully worked solutions must state governing thermodynamic principles, identify assumptions, define variables, show algebraic steps, include units where applicable, explain the physical meaning of the result, and connect the solution back to the MSE202 and MSE302 concepts being bridged.

For multiple-choice questions, include 4 plausible answer choices, avoid trivial distractors, identify exactly one correct answer, and explain why each distractor is incorrect.

For derivation-based questions, explain why each assumption is appropriate for an undergraduate thermodynamics treatment.

Assessment Quality Check must rate each criterion from 1 to 5 and include a short comment for:
1. Understanding of fundamental thermodynamic concepts
2. Alignment with the learning outcomes for MSE202 and MSE302
3. Consistency with the concept map linking MSE202 and MSE302
4. Appropriate difficulty for the specified level
5. Alignment with materials science interests and applications
6. Clarity and fairness of student-facing wording
7. Correct setup of derivations, assumptions, and undergraduate-appropriate methods

Suggested Revision Options must provide 2 to 3 concise instructor-facing ways to modify the question.

Equation handling:
- Mark every equation, derivation step, thermodynamic identity, chemical-potential expression, Gibbs-energy expression, equilibrium condition, and calculation formula in an equation fields array.
- Do not return equations as images or screenshots.
- Do not use markdown equation delimiters.
- Use notation that can be converted to native Word equation objects by the DOCX exporter.

Return only valid JSON with this shape:
{
  \"questions\": [
    {
      \"type\": \"mcq\" | \"long_answer\" | \"short_answer\",
      \"metadata\": {
        \"prompt_template_id\": \"...\",
        \"actual_prompt_id\": \"...\",
        \"output_id\": \"...\",
        \"final_question_id\": \"...\",
        \"question_title\": \"...\",
        \"difficulty_level\": \"...\",
        \"intended_assessment_setting\": \"...\",
        \"mse202_concepts\": [\"...\"],
        \"mse302_concepts\": [\"...\"],
        \"concept_map_bridge\": \"...\",
        \"materials_science_context\": \"...\",
        \"estimated_time\": \"...\",
        \"learning_objectives\": [\"...\"],
        \"id_requirements\": \"...\"
      },
      \"body\": \"...\",
      \"options\": [{\"body\": \"...\", \"is_correct\": true}],
      \"model_answer\": \"...\",
      \"equations\": [{\"label\": \"...\", \"expression\": \"...\", \"location\": \"question|solution\"}],
      \"quality_check\": [{\"criterion\": \"...\", \"rating\": 1, \"comment\": \"...\"}],
      \"revision_options\": [\"...\"]
    }
  ]
}
"""
```

- [ ] **Step 5: Implement prompt factors using the converted system prompt**

Create `backend/services/prompt_factors.py`:

```python
from backend.schemas.experiment_schema import PromptFactors, PromptStructure
from backend.services.research_system_prompt import BLUEPRINT_LAB_SYSTEM_PROMPT


def build_condition_label(factors: PromptFactors) -> str:
    return (
        f"CourseBridge={'ON' if factors.course_bridge else 'OFF'}; "
        f"FewShot={'ON' if factors.few_shot else 'OFF'}; "
        f"Documents={'ON' if factors.documents else 'OFF'}"
    )


def _factor_sections(factors: PromptFactors) -> str:
    sections: list[str] = []
    if factors.course_bridge:
        sections.append(
            "## Course Bridge\n"
            "Explicitly connect the MSE202 prerequisite concept to the MSE302 thermodynamics concept. "
            "Name the bridge in the metadata and use it in the worked solution."
        )
    if factors.few_shot:
        sections.append(
            "## Few-shot Examples\n"
            "Use any supplied example pattern as a style and rigor guide. Generate new assessment content for this experiment."
        )
    if factors.documents:
        sections.append(
            "## Instructor Examples / Attached Documents\n"
            "Treat instructor-provided examples as authoritative constraints on terminology, notation, scope, and solution style."
        )
    return "\n\n".join(sections)


def build_research_prompt(
    *,
    prompt_structure: PromptStructure,
    course: str,
    topic: str,
    learning_objectives: str,
    assessment_type: str,
    difficulty: str,
    number_of_questions: int,
    factors: PromptFactors,
) -> str:
    condition = build_condition_label(factors)
    shared = (
        f"Prompt Structure: {prompt_structure}\n"
        f"Experiment Condition: {condition}\n"
        f"Course: {course}\n"
        f"Topic: {topic}\n"
        f"Learning Objectives: {learning_objectives}\n"
        f"Assessment Type: {assessment_type}\n"
        f"Difficulty: {difficulty}\n"
        f"Number of Questions: {number_of_questions}\n"
    )
    factor_sections = _factor_sections(factors)

    if prompt_structure == "anthropic":
        return (
            "<role>\n"
            f"{BLUEPRINT_LAB_SYSTEM_PROMPT}\n"
            "</role>\n\n"
            "<task>\n"
            f"{shared}\n"
            "</task>\n\n"
            "<prompt_design_factors>\n"
            f"{factor_sections or 'No optional prompt design factors are enabled.'}\n"
            "</prompt_design_factors>\n\n"
            "<output_format>\n"
            "Return only valid JSON matching the system prompt schema.\n"
            "</output_format>"
        ).strip()

    return (
        "# Role\n"
        f"{BLUEPRINT_LAB_SYSTEM_PROMPT}\n\n"
        "# Goal\n"
        f"{shared}\n"
        "Generate assessment JSON for the configured Blueprint Lab experiment condition.\n\n"
        "# Prompt Design Factors\n"
        f"{factor_sections or 'No optional prompt design factors are enabled.'}\n\n"
        "# Measure of Success\n"
        "The output is valid JSON, traceable to the experiment condition, aligned with MSE202/MSE302 concepts, and ready for DOCX rendering.\n\n"
        "# Constraints\n"
        "Keep the prompt structure fixed. Only the listed prompt design factors may alter the generation context.\n\n"
        "# Output\n"
        "Return only valid JSON matching the system prompt schema.\n\n"
        "# Stop Rules\n"
        "If course, topic, learning objectives, or number of questions are missing, return a schema-valid error object."
    ).strip()
```

- [ ] **Step 6: Replace `generate_prompt` inputs**

Modify `backend/services/prompt_generator.py`:

```python
from backend.schemas.experiment_schema import PromptFactors, PromptStructure
from backend.services.prompt_factors import build_research_prompt


def generate_prompt(
    *,
    course: str,
    topic: str,
    learning_objectives: str,
    assessment_type: str,
    difficulty: str,
    number_of_questions: int,
    prompt_structure: PromptStructure,
    factors: PromptFactors,
) -> str:
    return build_research_prompt(
        prompt_structure=prompt_structure,
        course=course,
        topic=topic,
        learning_objectives=learning_objectives,
        assessment_type=assessment_type,
        difficulty=difficulty,
        number_of_questions=number_of_questions,
        factors=factors,
    )
```

- [ ] **Step 7: Run prompt tests**

Run:

```powershell
pytest backend/tests/test_research_system_prompt.py backend/tests/test_prompt_factors.py backend/tests/test_prompt_generator.py -v
```

Expected: update or delete old prompt-generator assertions for Forge/RISEN; new tests pass.

- [ ] **Step 8: Commit**

```powershell
git add backend/services/research_system_prompt.py backend/services/prompt_factors.py backend/services/prompt_generator.py backend/tests/test_research_system_prompt.py backend/tests/test_prompt_factors.py backend/tests/test_prompt_generator.py
git commit -m "refactor: adapt ChatGPT prompt for Blueprint Lab" -m "This converts the ChatGPT Web thermodynamics instructions into an application system prompt for structured Blueprint Lab generation. The prompt preserves MSE traceability, concept bridging, solution quality, equation metadata, and assessment-quality checks while removing chat-only download and response-marker behavior."
```

---

### Task 5: Generate Questions Directly From the Prompt

**Files:**
- Modify: `backend/services/generator.py`
- Test: `backend/tests/test_generator.py`

- [ ] **Step 1: Write direct generation test**

Replace planner-based generator tests with:

```python
from unittest.mock import MagicMock

from backend.services.generator import generate_questions


def test_generate_questions_uses_full_prompt_directly():
    llm = MagicMock()
    llm.generate_json.return_value = {
        "questions": [
            {
                "type": "mcq",
                "body": "What is stress?",
                "options": [
                    {"body": "Force per area", "is_correct": True},
                    {"body": "Force times area", "is_correct": False},
                    {"body": "Mass per volume", "is_correct": False},
                    {"body": "Velocity over time", "is_correct": False},
                ],
                "model_answer": None,
            }
        ]
    }

    result = generate_questions(llm=llm, generated_prompt="Generate a statics assessment.")

    assert result.questions[0].body == "What is stress?"
    _, kwargs = llm.generate_json.call_args
    assert kwargs["user_message"] == "Generate a statics assessment."
    assert "structured assessment plan" not in kwargs["system_prompt"]
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
pytest backend/tests/test_generator.py -v
```

Expected: FAIL because the current service expects `PlannerResponse`.

- [ ] **Step 3: Implement direct generator**

Modify `backend/services/generator.py`:

```python
from backend.schemas.assessment_schema import AssessmentGenerationResponse
from backend.services.llm_client import LLMClient


_QUESTION_GENERATOR_SYSTEM_PROMPT = """You are an expert undergraduate engineering assessment writer.

Generate the assessment directly from the provided prompt. Do not create or rely on a separate planning stage.

For MCQ questions:
- Write a clear, unambiguous question body
- Provide exactly 4 options: exactly one correct option and three plausible distractors
- Set model_answer to null

For short or long answer questions:
- Write a clear question body
- Set options to an empty array []
- Write a complete model_answer suitable for instructor use

Return only valid JSON matching this schema:
{
  "questions": [
    {
      "type": "mcq",
      "body": "...",
      "options": [{"body": "...", "is_correct": false}],
      "model_answer": null
    }
  ]
}
"""


def generate_questions(llm: LLMClient, generated_prompt: str) -> AssessmentGenerationResponse:
    raw = llm.generate_json(
        system_prompt=_QUESTION_GENERATOR_SYSTEM_PROMPT,
        user_message=generated_prompt,
    )
    return AssessmentGenerationResponse(**raw)
```

- [ ] **Step 4: Run generator tests**

Run:

```powershell
pytest backend/tests/test_generator.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/generator.py backend/tests/test_generator.py
git commit -m "refactor: generate questions directly from prompts" -m "This removes the planner dependency from question generation. The LLM now receives the generated research prompt directly, reducing an extra reasoning stage that would introduce unwanted experimental variation."
```

---

### Task 6: Add DOCX Generation as the Primary Artifact

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/services/docx_exporter.py`
- Test: `backend/tests/test_docx_exporter.py`

- [ ] **Step 1: Add dependency**

Add to `backend/requirements.txt`:

```text
python-docx==1.1.2
```

- [ ] **Step 2: Write DOCX exporter test**

Create `backend/tests/test_docx_exporter.py`:

```python
from io import BytesIO

from docx import Document

from backend.services.docx_exporter import build_assessment_docx


def test_docx_contains_research_metadata_and_solutions():
    content = build_assessment_docx(
        assessment_id=12,
        prompt_id=34,
        condition_label="CourseBridge=ON; FewShot=OFF; Documents=ON",
        course="ENGR 101",
        topic="Statics",
        questions=[
            {
                "type": "mcq",
                "body": "What is equilibrium?",
                "options": [{"body": "Net force is zero", "is_correct": True}],
                "model_answer": None,
            },
            {
                "type": "long_answer",
                "body": "Explain free-body diagrams.",
                "options": [],
                "model_answer": "A free-body diagram isolates a body and shows external loads.",
            },
        ],
    )

    document = Document(BytesIO(content))
    text = "\n".join(p.text for p in document.paragraphs)

    assert "Assessment ID: 12" in text
    assert "Prompt ID: 34" in text
    assert "CourseBridge=ON; FewShot=OFF; Documents=ON" in text
    assert "What is equilibrium?" in text
    assert "Solutions" in text
    assert "A free-body diagram isolates a body" in text
```

- [ ] **Step 3: Run the failing test**

Run:

```powershell
pytest backend/tests/test_docx_exporter.py -v
```

Expected: FAIL until `python-docx` is installed and the exporter exists.

- [ ] **Step 4: Implement DOCX exporter**

Create `backend/services/docx_exporter.py`:

```python
from io import BytesIO

from docx import Document


def build_assessment_docx(
    *,
    assessment_id: int,
    prompt_id: int,
    condition_label: str,
    course: str,
    topic: str,
    questions: list[dict],
) -> bytes:
    document = Document()
    document.add_heading("Blueprint Lab Assessment", level=1)
    document.add_paragraph(f"Assessment ID: {assessment_id}")
    document.add_paragraph(f"Prompt ID: {prompt_id}")
    document.add_paragraph(f"Experiment Condition: {condition_label}")
    document.add_paragraph(f"Course: {course}")
    document.add_paragraph(f"Topic: {topic}")

    document.add_heading("Generated Questions", level=2)
    for index, question in enumerate(questions, start=1):
        document.add_paragraph(f"Q{index}. {question['body']}")
        for option in question.get("options", []):
            suffix = " [correct]" if option.get("is_correct") else ""
            document.add_paragraph(f"- {option['body']}{suffix}")

    document.add_heading("Solutions", level=2)
    for index, question in enumerate(questions, start=1):
        answer = question.get("model_answer")
        if answer:
            document.add_paragraph(f"Q{index}. {answer}")
        else:
            correct = [o["body"] for o in question.get("options", []) if o.get("is_correct")]
            document.add_paragraph(f"Q{index}. {correct[0] if correct else 'No solution provided.'}")

    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()
```

- [ ] **Step 5: Run DOCX tests**

Run:

```powershell
pip install -r backend/requirements.txt
pytest backend/tests/test_docx_exporter.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/requirements.txt backend/services/docx_exporter.py backend/tests/test_docx_exporter.py
git commit -m "feat: generate Word assessment artifacts" -m "This adds DOCX generation as the primary Blueprint Lab output. The document embeds assessment, prompt, experiment condition, course, topic, generated questions, and solutions so exported assessments remain traceable without checking the database."
```

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

---

### Task 10: Migrate Frontend Types, Store, and API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/experiments.ts`
- Create: `frontend/src/api/generations.ts`
- Modify: `frontend/src/store/runStore.ts`
- Test: `frontend/src/App.test.tsx` or create focused store tests if existing test setup supports it.

- [ ] **Step 1: Replace frontend type model**

Modify `frontend/src/types/index.ts`:

```ts
export type Stage =
  | 'pending'
  | 'prompting'
  | 'generating'
  | 'documenting'
  | 'complete'
  | 'error'

export type PromptStructure = 'openai' | 'anthropic'

export interface PromptFactors {
  course_bridge: boolean
  few_shot: boolean
  documents: boolean
}

export interface Condition {
  id: number
  prompt_structure: PromptStructure
  course_bridge_enabled: boolean
  few_shot_enabled: boolean
  documents_enabled: boolean
  condition_label: string
}

export interface Generation {
  id: number
  condition_id: number
  status: Stage
  model_name?: string | null
  model_version?: string | null
  generation_time_ms?: number | null
  generated_json?: { questions: Question[] } | null
  condition?: Condition
  prompt_text?: string | null
}

export interface Experiment {
  id: number
  course: string
  topic: string
  learning_objectives: string
  assessment_type: 'mcq' | 'short_answer' | 'mixed'
  difficulty: string
  number_of_questions: number
  created_at: string
  conditions: Condition[]
  generations: Generation[]
}

export interface MCQOption {
  id?: number
  body: string
  is_correct: boolean
}

export interface Question {
  id?: number
  type: 'mcq' | 'long_answer' | 'short_answer'
  body: string
  order?: number
  options?: MCQOption[]
  model_answer?: string | null
}

export interface SSEEvent {
  generation_id: number
  condition_id: number
  stage: Stage
}

export interface CreateExperimentPayload {
  course: string
  topic: string
  learning_objectives: string
  assessment_type: 'mcq' | 'short_answer' | 'mixed'
  difficulty: string
  number_of_questions: number
  prompt_structure: PromptStructure
  factors: PromptFactors
}
```

- [ ] **Step 2: Add experiment and generation clients**

Create `frontend/src/api/experiments.ts`:

```ts
import { api } from './client'
import type { CreateExperimentPayload, Experiment } from '../types'

export const experimentsApi = {
  create: (payload: CreateExperimentPayload): Promise<Experiment> =>
    api.post('/experiments', payload),

  get: (id: number): Promise<Experiment> =>
    api.get(`/experiments/${id}`),
}
```

Create `frontend/src/api/generations.ts`:

```ts
import { api } from './client'
import type { Generation } from '../types'

export const generationsApi = {
  get: (id: number): Promise<Generation> =>
    api.get(`/generations/${id}`),

  regenerate: (id: number): Promise<{ generation_id: number; status: string }> =>
    api.post(`/generations/${id}/regenerate`, {}),

  exportDocx: async (id: number): Promise<void> => {
    const res = await fetch(`/api/generations/${id}/export-docx`)
    if (!res.ok) throw new Error('DOCX export failed')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `blueprint-lab-generation-${id}.docx`
    a.click()
    URL.revokeObjectURL(url)
  },
}
```

- [ ] **Step 3: Replace store state names**

Modify `frontend/src/store/runStore.ts` or rename later to `experimentStore.ts`. Minimal first pass:

```ts
import { create } from 'zustand'
import type { Experiment, Generation, SSEEvent } from '../types'

interface ExperimentStore {
  experiment: Experiment | null
  generations: Record<number, Generation>
  selectedGenerationId: number | null
  setExperiment: (experiment: Experiment) => void
  applySSEEvent: (event: SSEEvent) => void
  setGeneration: (generation: Generation) => void
  selectGeneration: (id: number) => void
  reset: () => void
}

export const useRunStore = create<ExperimentStore>((set) => ({
  experiment: null,
  generations: {},
  selectedGenerationId: null,

  setExperiment: (experiment) => {
    const generations: Record<number, Generation> = {}
    experiment.generations.forEach(g => { generations[g.id] = g })
    set({ experiment, generations, selectedGenerationId: null })
  },

  applySSEEvent: (event) => set((state) => {
    const existing = state.generations[event.generation_id]
    if (!existing) return state
    const updated = { ...existing, status: event.stage }
    return {
      generations: { ...state.generations, [existing.id]: updated },
      selectedGenerationId:
        state.selectedGenerationId === null && event.stage === 'complete'
          ? existing.id
          : state.selectedGenerationId,
    }
  }),

  setGeneration: (generation) => set((state) => ({
    generations: { ...state.generations, [generation.id]: generation },
  })),

  selectGeneration: (id) => set({ selectedGenerationId: id }),

  reset: () => set({ experiment: null, generations: {}, selectedGenerationId: null }),
}))
```

- [ ] **Step 4: Run frontend checks**

Run:

```powershell
cd frontend
npm test -- --run
npm run build
```

Expected: fix type errors before continuing.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/types/index.ts frontend/src/api/experiments.ts frontend/src/api/generations.ts frontend/src/store/runStore.ts
git commit -m "refactor: migrate frontend data model to experiments" -m "This updates the frontend client state and API types from assessment runs to Blueprint Lab experiments, conditions, and generations. The browser now models progress events by generation ID and prepares the UI for condition metadata and DOCX export."
```

---

### Task 11: Simplify the Frontend Input Flow for Research Variables

**Files:**
- Modify: `frontend/src/pages/InputPanelPage.tsx`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step 1: Replace production controls**

Modify `InputPanelPage.tsx` so the form state is:

```ts
interface FormState {
  course: string
  topic: string
  learningObjectives: string
  assessmentType: 'mcq' | 'short_answer' | 'mixed'
  difficulty: string
  promptStructure: 'openai' | 'anthropic'
  courseBridge: boolean
  fewShot: boolean
  documents: boolean
  numberOfQuestions: string
}
```

Remove production controls for subject area, academic level, Bloom dropdown, language register, variants, word count, shuffling, and PDF defaults.

- [ ] **Step 2: Submit experiment payload**

Use `experimentsApi.create`:

```ts
const experiment = await experimentsApi.create({
  course: form.course.trim(),
  topic: form.topic.trim(),
  learning_objectives: form.learningObjectives.trim(),
  assessment_type: form.assessmentType,
  difficulty: form.difficulty,
  number_of_questions: parseInt(form.numberOfQuestions) || 4,
  prompt_structure: form.promptStructure,
  factors: {
    course_bridge: form.courseBridge,
    few_shot: form.fewShot,
    documents: form.documents,
  },
})
navigate(`/experiments/${experiment.id}/progress`)
```

- [ ] **Step 3: Rename visible product text**

Use:

```text
Blueprint Lab
New Experiment
Run Experiment
Prompt Design Factors
```

Do not show Forge, RISEN, production pedagogical controls, or PDF as the primary export.

- [ ] **Step 4: Run frontend checks**

Run:

```powershell
cd frontend
npm test -- --run
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/pages/InputPanelPage.tsx frontend/src/App.test.tsx
git commit -m "refactor: simplify experiment input workflow" -m "This replaces production-oriented assessment controls with research inputs for Blueprint Lab. Users now configure course, topic, objectives, assessment type, difficulty, prompt structure, prompt design factors, and question count before running an experiment."
```

---

### Task 12: Migrate Progress and Viewer Pages

**Files:**
- Modify: `frontend/src/hooks/useSSE.ts`
- Modify: `frontend/src/pages/ProgressPage.tsx`
- Modify: `frontend/src/pages/AssessmentViewerPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Update routes**

Modify `frontend/src/App.tsx`:

```tsx
<Route path="/" element={<InputPanelPage />} />
<Route path="/experiments/:experimentId/progress" element={<ProgressPage />} />
<Route path="/experiments/:experimentId/viewer" element={<AssessmentViewerPage />} />
```

- [ ] **Step 2: Update SSE hook endpoint**

Modify `frontend/src/hooks/useSSE.ts` to connect to:

```ts
`/api/experiments/${experimentId}/progress`
```

- [ ] **Step 3: Update progress page language and stages**

Use stage labels:

```ts
const stageConfig = {
  pending: { label: 'Queued' },
  prompting: { label: 'Generating prompt' },
  generating: { label: 'Generating questions' },
  documenting: { label: 'Building Word document' },
  complete: { label: 'Complete' },
  error: { label: 'Failed' },
}
```

Display each generation by `condition.condition_label` and prompt structure.

- [ ] **Step 4: Update viewer page**

Use `generationsApi.get`, `generationsApi.regenerate`, and `generationsApi.exportDocx`. Show:

```text
Assessment ID
Prompt ID or prompt preview
Experiment Condition
Course
Topic
Generated Questions
Solutions
```

The primary export button should call `exportDocx`. PDF can remain hidden or secondary.

- [ ] **Step 5: Run frontend checks**

Run:

```powershell
cd frontend
npm test -- --run
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/App.tsx frontend/src/hooks/useSSE.ts frontend/src/pages/ProgressPage.tsx frontend/src/pages/AssessmentViewerPage.tsx
git commit -m "refactor: show experiments and generations in the UI" -m "This updates the progress and review screens to use Blueprint Lab experiment language. Generations are now tracked by condition metadata, progress reflects the simplified research pipeline, and DOCX is presented as the primary export."
```

---

### Task 13: Remove Planner, Validation, and Removed Frameworks

**Files:**
- Delete: `backend/services/planner.py`
- Delete: `backend/services/validator.py`
- Delete: `backend/schemas/planner_schema.py`
- Delete or archive: `forge-skills/`
- Delete or archive: `prompt/RISEN-skills/`
- Modify: `backend/services/framework_templates.py` or delete if unused.
- Modify tests that import these modules.

- [ ] **Step 1: Search for remaining planner/framework references**

Run:

```powershell
rg "planner|Planner|validator|validate_plan|forge|RISEN|risen|ControlSet|framework" backend frontend README.md docs
```

Expected: references only in historical plan/spec docs, or none in runtime code.

- [ ] **Step 2: Delete planner and validator runtime files**

Use `apply_patch` or normal git-aware file removal:

```powershell
git rm backend/services/planner.py backend/services/validator.py backend/schemas/planner_schema.py
```

- [ ] **Step 3: Remove old prompt framework assets**

If the fork no longer needs production assets:

```powershell
git rm -r forge-skills prompt/RISEN-skills
```

Keep `prompt/openai-skills/` only if it is referenced as documentation. Otherwise remove `prompt/` after confirming no runtime dependency.

- [ ] **Step 4: Remove obsolete tests**

Remove or rewrite:

```powershell
git rm backend/tests/test_planner.py backend/tests/test_validator.py backend/tests/test_framework_templates.py
```

- [ ] **Step 5: Run full backend tests**

Run:

```powershell
pytest backend/tests -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add -A
git commit -m "refactor: remove planner and production prompt frameworks" -m "This deletes the planner, planner validation, and removed production framework assets from the Blueprint Lab fork. The runtime now exposes only the controlled research prompt structures and avoids an extra LLM reasoning stage."
```

---

### Task 14: Rename Product Documentation and App Metadata

**Files:**
- Modify: `README.md`
- Modify: `backend/main.py`
- Modify: `frontend/index.html`
- Modify: `frontend/package.json`
- Search/modify visible strings in `frontend/src`

- [ ] **Step 1: Search product names**

Run:

```powershell
rg "Blueprint|Design Blueprint|Assessment Generator|assessment generator|Generate Assessment|Assessment Run" README.md backend frontend
```

Expected: identify visible strings requiring rename.

- [ ] **Step 2: Update backend app title**

In `backend/main.py`:

```python
app = FastAPI(title="Blueprint Lab")
```

- [ ] **Step 3: Update frontend app metadata**

In `frontend/index.html`, use:

```html
<title>Blueprint Lab</title>
```

In `frontend/package.json`, use a package name such as:

```json
"name": "blueprint-lab-frontend"
```

- [ ] **Step 4: Replace visible app language**

Use research platform terms:

```text
Blueprint Lab
Experiment
Condition
Generation
Prompt Design Factors
Word document
```

- [ ] **Step 5: Rewrite README**

README should state:

```markdown
# Blueprint Lab

Blueprint Lab is a controlled research platform for prompt-engineering experiments on undergraduate engineering assessment generation. It prioritizes reproducibility, experimental control, metadata logging, and research usability over production flexibility.
```

Include the new pipeline:

```text
Prompt Generation -> Question Generation -> Word Document Generation -> Metadata Logging -> Persistence
```

- [ ] **Step 6: Commit**

```powershell
git add README.md backend/main.py frontend/index.html frontend/package.json frontend/src
git commit -m "docs: rename project to Blueprint Lab" -m "This updates product naming and documentation for the research-platform fork. The README and visible app metadata now describe Blueprint Lab as a controlled prompt-engineering experiment platform rather than a general-purpose assessment generator."
```

---

### Task 15: Full Verification

**Files:**
- No planned source edits unless tests fail.

- [ ] **Step 1: Run backend tests**

Run:

```powershell
pytest backend/tests -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests and build**

Run:

```powershell
cd frontend
npm test -- --run
npm run build
```

Expected: PASS.

- [ ] **Step 3: Start local services for manual smoke test**

Run Redis and Celery as normally configured, then:

```powershell
uvicorn backend.main:app --reload
cd frontend
npm run dev
```

Manual path:

1. Open `http://localhost:5173`.
2. Create a Blueprint Lab experiment with OpenAI prompt structure.
3. Enable Course Bridge and Documents, leave Few-shot off.
4. Confirm progress stages are `prompting`, `generating`, `documenting`, `complete`.
5. Open the viewer.
6. Export DOCX.
7. Open the Word document and confirm it contains Assessment ID, Prompt ID, condition metadata, course, topic, questions, and solutions.

- [ ] **Step 4: Final reference search**

Run:

```powershell
rg "planner|Planner|validating|Forge|RISEN|Design Blueprint|PDF export" backend frontend README.md
```

Expected: no runtime UI/API references. Historical docs may still mention old terms.

- [ ] **Step 5: Commit any verification fixes**

If fixes were required:

```powershell
git add -A
git commit -m "fix: complete Blueprint Lab migration verification" -m "This addresses issues found during full backend, frontend, and manual smoke-test verification of the Blueprint Lab migration. The fixes keep the research workflow consistent across API, worker, UI, and exported Word artifacts."
```

---

## Self-Review

- Spec coverage: The plan covers renaming, planner removal, fixed OpenAI/optional Anthropic structures, independently toggled prompt design factors, simplified inputs, DOCX primary output, full metadata logging, condition traceability, future rubric scoring, database simplification, retained FastAPI/React/Celery/SSE/persistence/regeneration, and the core abstraction shift to experiment/condition/generation/evaluation.
- Known implementation choice: The plan keeps old filenames such as `assessment_worker.py` temporarily to reduce Celery import churn. A later cleanup can rename files after the migration is stable.
- Risk: Existing SQLite data is not migrated. This is acceptable for a forked research platform unless production data must be retained. If retention is required, add an Alembic/data migration task before deleting old models.
- Dependency risk: `python-docx` must be installed before DOCX tests pass.
