# Blueprint Lab Research Platform Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fork Blueprint into Blueprint Lab, a controlled research platform where users run experiment conditions that generate reproducible engineering assessments with complete prompt, factor, model, document, and evaluation metadata.

**Architecture:** Replace the current `Run -> ControlSet -> Assessment` workflow with `Experiment -> Condition -> Generation -> Evaluation`, while preserving FastAPI, React, Celery, Redis progress events, database persistence, regeneration, and export behavior. Remove the planner stage entirely so the LLM path is prompt generation, question generation, DOCX generation, metadata logging, and persistence.

For prompt generation, keep one canonical Blueprint Lab assessment system prompt and JSON output schema. Render research inputs into provider-specific structures: Anthropic prompts must use the exact `<context>`, `<task>`, `<constraints>`, `<verification>`, `<output_format>`, and `<reasoning_guidance>` XML sections defined in `prompt/anthropic-skills/src/reference/prompt-structure.md`; OpenAI prompts use the corresponding Markdown sections. Pass the generated provider-specific prompt directly to question generation without a planner or a second competing assessment schema.

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
yes

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


def test_anthropic_prompt_uses_reference_xml_structure():
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

    assert "<context>" in prompt
    assert "<task>" in prompt
    assert "<constraints>" in prompt
    assert "<verification>" in prompt
    assert "<output_format>" in prompt
    assert "<reasoning_guidance>" in prompt
    assert "<role>" not in prompt
    assert "<prompt_design_factors>" not in prompt
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


The application will create the .docx artifact after you return structured JSON.

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
            "<context>\n"
            f"{BLUEPRINT_LAB_SYSTEM_PROMPT}\n\n{shared}\n"
            f"{factor_sections or 'No optional prompt design factors are enabled.'}\n"
            "</context>\n\n"
            "<task>\n"
            "Generate the requested instructor-ready MSE thermodynamics assessment questions directly. "
            "Do not create a separate assessment plan.\n"
            "</task>\n\n"
            "<constraints>\n"
            "Keep the prompt structure fixed. Only enabled prompt-design factors may alter the generation context. "
            "Preserve supplied traceability IDs exactly and do not invent missing IDs.\n"
            "</constraints>\n\n"
            "<verification>\n"
            "Before returning, verify thermodynamic correctness, unit consistency, MSE202/MSE302 alignment, "
            "schema completeness, and exactly one correct option for every MCQ.\n"
            "</verification>\n\n"
            "<output_format>\n"
            "Return only valid JSON matching the system prompt schema. Include metadata, worked solutions, "
            "equations, quality checks, and revision options for every question.\n"
            "</output_format>\n\n"
            "<reasoning_guidance>\n"
            "Develop each question in stages: establish the course-concept bridge, construct the student-facing "
            "problem, solve it completely, verify it, and then serialize only the final structured result.\n"
            "</reasoning_guidance>"
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
                "metadata": {
                    "prompt_template_id": "Not Assigned",
                    "actual_prompt_id": "Not Assigned",
                    "output_id": "Not Assigned",
                    "final_question_id": "Not Assigned",
                    "question_title": "Stress definition",
                    "difficulty_level": "introductory",
                    "intended_assessment_setting": "homework",
                    "mse202_concepts": ["stress"],
                    "mse302_concepts": ["mechanical work"],
                    "concept_map_bridge": "Relates force intensity to mechanical work terms.",
                    "materials_science_context": "Supports mechanics of materials reasoning.",
                    "estimated_time": "2 minutes",
                    "learning_objectives": ["Define engineering stress."],
                    "id_requirements": "No IDs supplied.",
                },
                "body": "What is stress?",
                "options": [
                    {"body": "Force per area", "is_correct": True},
                    {"body": "Force times area", "is_correct": False},
                    {"body": "Mass per volume", "is_correct": False},
                    {"body": "Velocity over time", "is_correct": False},
                ],
                "model_answer": None,
                "equations": [],
                "quality_check": [
                    {"criterion": "Thermodynamic correctness", "rating": 5, "comment": "Correct."}
                ],
                "revision_options": ["Make the question computational."],
            }
        ]
    }

    result = generate_questions(llm=llm, generated_prompt="Generate a statics assessment.")

    assert result.questions[0].body == "What is stress?"
    _, kwargs = llm.generate_json.call_args
    assert kwargs["user_message"] == "Generate a statics assessment."
    assert "structured assessment plan" not in kwargs["system_prompt"]
    assert "Do not add, remove, or reinterpret" in kwargs["system_prompt"]
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


_QUESTION_GENERATOR_SYSTEM_PROMPT = """Execute the provided generated research prompt directly.

Do not create or rely on a separate planning stage. Do not add, remove, or reinterpret provider-specific
prompt sections. Follow the JSON schema embedded in the generated prompt and return only valid JSON.
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
git commit -m "refactor: generate questions directly from prompts" -m "This removes the planner dependency from question generation. The LLM now receives the generated Anthropic- or OpenAI-structured research prompt directly and follows its canonical rich JSON schema, avoiding an extra reasoning stage or a conflicting generator schema that would introduce unwanted experimental variation."
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
                "metadata": {
                    "question_title": "Equilibrium",
                    "concept_map_bridge": "Connects force balance to equilibrium reasoning.",
                },
                "body": "What is equilibrium?",
                "options": [{"body": "Net force is zero", "is_correct": True}],
                "model_answer": None,
                "equations": [{"label": "Balance", "expression": "sum F = 0", "location": "solution"}],
                "quality_check": [{"criterion": "Clarity", "rating": 5, "comment": "Unambiguous."}],
                "revision_options": ["Add a materials-specific scenario."],
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
    assert "Connects force balance to equilibrium reasoning." in text
    assert "sum F = 0" in text
    assert "Assessment Quality Check" in text
    assert "Suggested Revision Options" in text
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
        metadata = question.get("metadata", {})
        if metadata.get("question_title"):
            document.add_heading(metadata["question_title"], level=3)
        if metadata.get("concept_map_bridge"):
            document.add_paragraph(f"Concept-Map Bridge: {metadata['concept_map_bridge']}")
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

        for equation in question.get("equations", []):
            document.add_paragraph(f"{equation['label']}: {equation['expression']}")

    document.add_heading("Assessment Quality Check", level=2)
    for index, question in enumerate(questions, start=1):
        for check in question.get("quality_check", []):
            document.add_paragraph(
                f"Q{index} - {check['criterion']}: {check['rating']}/5 - {check['comment']}"
            )

    document.add_heading("Suggested Revision Options", level=2)
    for index, question in enumerate(questions, start=1):
        for revision in question.get("revision_options", []):
            document.add_paragraph(f"Q{index}: {revision}")

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

-
