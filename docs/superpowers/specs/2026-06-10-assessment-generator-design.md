# Assessment Generator — Design Spec

**Date:** 2026-06-10
**Status:** Approved

---

## Overview

A web application for professors and teaching teams that automatically generates educational assessments. The instructor provides a topic or chapter and a short description of what the questions should test. The system generates 12 assessments in parallel — one per combination of three prompt frameworks and four instructor-configured control variable sets — using a three-call LLM pipeline per assessment. Results are displayed interactively on the web and exportable as PDF.

The existing `forge-benchmark-prompt` skill serves as a structural reference for the Forge framework prompt template.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React (Vite) |
| Backend | FastAPI (Python) |
| Database | SQLite via SQLAlchemy (swap to Postgres for v2) |
| Job queue | Celery + Redis |
| LLM | Gemma 4-31b |
| PDF generation | WeasyPrint (server-side, Python) |
| State management | Zustand |
| HTTP client | Axios or fetch (React → FastAPI) |

---

## Generation Pipeline

Each of the 12 assessments passes through four sequential stages:

**Call 1 — Prompt Generator**
Input: instructor topic + expectations + framework template + control variable set
Output: `{ "generated_prompt": "..." }` — the actual prompt text to be used for assessment generation

**Call 2 — Planner**
Input: generated prompt from Call 1
Output: structured plan — question topics, cognitive level (Bloom's action word) per question, expected answer scope

```json
{
  "assessment_plan": {
    "questions": [
      {
        "type": "mcq",
        "bloom_level": "Analyze",
        "topic": "TCP Handshake",
        "answer_scope": "2-3 sentences"
      }
    ]
  }
}
```

**Validation — Plan Gate**
Before Call 3, the planner output is validated against the run config:
- MCQ count matches requested count
- Long answer count matches requested count
- No repeated question topics
- Bloom levels distributed (no single level exceeding 60% of questions)
- Answer scope values are non-empty strings

If validation fails, the assessment transitions to `error` status. Call 3 is not attempted on an invalid plan.

**Call 3 — Generator**
Input: validated plan from Call 2
Output: full structured assessment

```json
{
  "questions": [
    {
      "type": "mcq",
      "body": "...",
      "options": [
        { "body": "...", "is_correct": false },
        { "body": "...", "is_correct": true },
        { "body": "...", "is_correct": false },
        { "body": "...", "is_correct": false }
      ],
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
```

All 12 assessment pipelines run in parallel via Celery workers. Wall-clock time is bounded by the slowest chain (not the sum of all 36 calls).

Every call response is validated against its Pydantic schema. FastAPI rejects malformed responses immediately rather than persisting invalid state.

---

## Prompt Frameworks

Three frameworks are supported. All three are selected by default and individually toggleable per run.

**Forge-skills framework**
Sections: `<context>`, `<task>`, `<constraints>`, `<verification>`, `<output_format>`, `<reasoning_guidance>`

**OpenAI-style framework**
Sections: `<role>`, `<personality>`, `<goal>`, `<measure_of_success>`, `<constraints>`, `<output>`, `<stop_rules>`

**RISEN framework**
Sections: `<role>`, `<instructions>`, `<step>`, `<end_goal>`, `<narrowing>`

---

## Control Variables

Each run has four instructor-configured control variable sets. Each set is a combination of:

| Variable | Options |
|---|---|
| Personality | Formal, Socratic, Encouraging, Challenging |
| Prompt length | Short / Medium / Long |
| Result length | Short / Medium / Long |
| Action word count | 1–5 (slider) |

With 3 frameworks × 4 control sets = **12 assessments per run**.

---

## Input Panel

The instructor configures a run with the following fields:

- **Topic / Chapter** — free text
- **Expectations** — free text (what should the questions test?)
- **MCQ count** — number input, default 10
- **Long answer count** — number input, default 3
- **Control variable sets** — 4 configurable rows (personality, prompt length, result length, action word count)
- **Frameworks** — 3 checkboxes, all selected by default

Submitting the form creates a Run record, enqueues 12 Celery jobs, and opens an SSE connection for progress. The progress panel shows per-assessment stage status as results stream in. The first assessment to reach `complete` is automatically loaded into the primary panel.

---

## Assessment Viewer Layout

```
┌─────────────────────────────────────────────────────────────┐
│  TOOLBAR: [Pin for Export] [Regenerate] [Export PDF ▾]      │
├──────────────────┬──────────────────────────────────────────┤
│  COMPARISON      │  PRIMARY PANEL                           │
│  SIDEBAR         │                                          │
│                  │  Framework: RISEN                        │
│  ▶ Forge /       │  Control: Socratic / Long / 4 words      │
│    Socratic/Lg   │                                          │
│  ▶ Forge /       │  Q1. [MCQ] ...                           │
│    Formal/Sh     │      ○ Option A                          │
│  ▶ OpenAI /      │      ○ Option B                          │
│    ...           │      ○ Option C                          │
│  ▶ RISEN /       │      ○ Option D                          │
│    ...           │      [Show model answer]                 │
│  (11 cards)      │                                          │
│                  │  Q11. [Long answer] ...                  │
│                  │      [textarea]                          │
│                  │      Word guide: ~200 words              │
│                  │      [Show model answer]                 │
└──────────────────┴──────────────────────────────────────────┘
```

**Toolbar (top):** Pin button, Regenerate button (reruns the assessment currently in the primary panel), Export PDF dropdown (Student version / Answer key version).

**Comparison sidebar (left):** 11 collapsed cards. Each card shows framework name + control set summary and a one-line preview of the first question. Clicking swaps that assessment into the primary panel.

**Primary panel (center/right):** Selected assessment rendered interactively. MCQs as radio buttons. Long answers as expandable textareas with a word count guide. Per-question "Show model answer" toggle.

---

## Real-Time Progress

The SSE stream from `POST /runs` emits one event per stage transition per assessment:

```json
{
  "assessment_id": 8,
  "framework": "forge",
  "control_set": 2,
  "stage": "planning"
}
```

The frontend renders a progress grid showing each of the 12 assessments at its current stage, e.g.:

```
Assessment 1  ✓ Prompt  ✓ Plan  ✓ Validate  ✓ Generate  ✓
Assessment 2  ✓ Prompt  ✓ Plan  ✓ Validate  ⟳ Generate
Assessment 3  ✓ Prompt  ⟳ Plan
Assessment 4  ⟳ Prompt
```

---

## PDF Export

Two export variants, selectable from the toolbar dropdown:

- **Student version** — questions only, MCQ options listed, blank lines for long answers, no model answers
- **Answer key version** — same layout with correct MCQ option marked and model answers included

Rendered server-side via WeasyPrint from an HTML/CSS template in `/api/export-pdf`.
Filename: `[topic]-[framework]-[control-set].pdf`

---

## Data Model

```
Run
  id
  topic
  expectations
  mcq_count         (default: 10)
  long_answer_count (default: 3)
  created_at

ControlSet            (4 per Run)
  id
  run_id
  personality         (formal | socratic | encouraging | challenging)
  prompt_length       (short | medium | long)
  result_length       (short | medium | long)
  action_word_count   (1–5)

Assessment            (12 per Run)
  id
  run_id
  framework           (forge | openai | risen)
  control_set_id
  status              (pending | prompting | planning | generating | validating | complete | error)
  created_at

PromptGeneration      (1 per Assessment)
  id
  assessment_id
  prompt_text
  created_at

PlannerOutput         (1 per Assessment)
  id
  assessment_id
  plan_json           (JSON)
  validation_passed   (boolean)
  validation_errors   (JSON, nullable)
  created_at

AssessmentGeneration  (1 per Assessment)
  id
  assessment_id
  raw_json            (JSON)
  created_at

Question
  id
  assessment_id
  type                (mcq | long_answer)
  body
  order

MCQOption
  id
  question_id
  body
  is_correct

ModelAnswer
  id
  question_id
  body
```

Separating `PromptGeneration`, `PlannerOutput`, and `AssessmentGeneration` into dedicated tables allows independent inspection of failures at each pipeline stage and supports future prompt engineering analysis across runs.

---

## API Routes

| Route | Method | Purpose |
|---|---|---|
| `POST /runs` | POST | Creates run, enqueues 12 Celery jobs, streams per-assessment stage progress via SSE |
| `GET /runs/{id}` | GET | Retrieves a stored run with all 12 assessments |
| `GET /assessments/{id}` | GET | Retrieves a single assessment |
| `POST /assessments/{id}/export-pdf` | POST | Returns PDF file (student or answer key variant) |
| `POST /assessments/{id}/regenerate` | POST | Reruns the 3-call pipeline for one assessment |

---

## Background Job Queue

`POST /runs` does not execute LLM calls synchronously. It creates the Run and ControlSet records, enqueues 12 Celery tasks (one per assessment), and immediately returns the run ID. The SSE connection provides live progress.

Each Celery task executes the full 3-call pipeline for one assessment (Prompt → Plan → Validate → Generate), writing stage records to the database and emitting SSE events at each transition.

This ensures a server restart during generation does not lose in-progress work — Celery can resume or retry failed tasks.

---

## Why Three LLM Calls (Not One)

A single prompt asking for 10 MCQs + 3 long answers in one shot gives the LLM too much latitude — it drifts, repeats cognitive levels, and pads answers. The three-call structure:

1. Separates prompt construction from content generation (Call 1 is meta-generation)
2. Forces the LLM to commit to a question structure before filling it in (Call 2 plan)
3. Keeps each call smaller and more focused, which reduces hallucination
4. Makes the plan inspectable and validatable before generation begins

---

## Backend Structure

```
backend/
│
├── api/
│   ├── runs.py
│   └── assessments.py
│
├── services/
│   ├── prompt_generator.py
│   ├── planner.py
│   ├── validator.py
│   └── generator.py
│
├── workers/
│   └── assessment_worker.py
│
├── models/
│   ├── run.py
│   ├── assessment.py
│   └── question.py
│
├── schemas/
│   ├── prompt_schema.py
│   ├── planner_schema.py
│   └── assessment_schema.py
│
├── templates/
│   └── pdf/
│
└── main.py
```

---

## Out of Scope

- User authentication (single shared instance for a teaching team)
- Student-facing assessment delivery (instructors export and distribute manually)
- Automated scoring of student responses
- LLM provider switching (Gemma 4-31b only)

---

## V2 Notes

V2 (planned ~one month after v1 launch) will add RAG and fine-tuning capabilities. The FastAPI + SQLAlchemy stack is chosen specifically to make this extension straightforward:
- RAG: add vector store (ChromaDB or pgvector), embedding pipeline, retrieval routes
- Fine-tuning: add HuggingFace Transformers training jobs as background tasks
- Database: migrate SQLite → Postgres to support pgvector and concurrent writes

The split pipeline tables (`PromptGeneration`, `PlannerOutput`, `AssessmentGeneration`) also produce a research-quality dataset across runs: framework × control variable × prompt × plan × final assessment, enabling post-hoc analysis of question diversity, Bloom level distribution, and difficulty variation by configuration.
