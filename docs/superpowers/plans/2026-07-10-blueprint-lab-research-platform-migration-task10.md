# Blueprint Lab Research Platform Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fork Blueprint into Blueprint Lab, a controlled research platform where users run experiment conditions that generate reproducible engineering assessments with complete prompt, factor content, model, document, and evaluation metadata.

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
- Create `frontend/src/components/PromptFactorFields.tsx` for accessible multi-select factor controls and conditional factor-content inputs.
- Modify `README.md` to describe Blueprint Lab and the research workflow.

## Global Frontend Constraints

- Keep course name, topic, learning objectives, assessment format, difficulty, number of questions, and estimated student completion time.
- Remove subject area, academic level, Bloom/question framework, language register, variants, word-count controls, shuffling, and PDF defaults.
- Treat Concept Bridge, Few-shot Examples, Reference Content, and Reasoning Guidance as independently selectable prompt design factors.
- Label the fourth factor `Reasoning Guidance (chain-of-thought condition)`, but request concise rationale or structured solution steps rather than hidden private model reasoning.
- Give every selected factor its own content box and persist the exact submitted content with the condition and prompt metadata.
- Use a single scrollable input page with inline validation, accessible controls, a condition summary, and a working `Run Experiment` action.
- Do not display inactive controls such as Save Draft unless the underlying behavior is implemented.

---

## Prerequisite Fork Plan

Task 1 is now its own setup plan: `docs/superpowers/plans/2026-07-09-blueprint-lab-forking.md`.

Execute that plan before starting this migration. This migration plan assumes all source edits happen in the standalone Blueprint Lab repository at `C:\Users\yeekw\Documents\Blueprint-Lab`, with its own `origin` remote and the original Blueprint repository kept only as optional `upstream` lineage.


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
  concept_bridge: boolean
  few_shot: boolean
  reference_content: boolean
  reasoning_guidance: boolean
}

export interface PromptFactorInputs {
  concept_bridge?: string
  few_shot?: string
  reference_content?: string
  reasoning_guidance?: string
}

export interface Condition {
  id: number
  prompt_structure: PromptStructure
  concept_bridge_enabled: boolean
  few_shot_enabled: boolean
  reference_content_enabled: boolean
  reasoning_guidance_enabled: boolean
  factor_inputs: PromptFactorInputs
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
  estimated_time_minutes: number
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
  factor_inputs: PromptFactorInputs
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
- Create: `frontend/src/components/PromptFactorFields.tsx`
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
  numberOfQuestions: string
  estimatedTimeMinutes: string
  promptStructure: 'openai' | 'anthropic'
  conceptBridge: boolean
  fewShot: boolean
  referenceContent: boolean
  reasoningGuidance: boolean
  conceptBridgeContent: string
  fewShotContent: string
  referenceContentText: string
  reasoningGuidanceContent: string
}
```

Remove production controls for subject area, academic level, Bloom dropdown, language register, variants, word count, shuffling, and PDF defaults.

Render the reduced workflow on one scrollable page with three sections:

1. `Assessment Details`: course, topic, objectives, format, difficulty, question count, and estimated student completion time.
2. `Prompt Design Factors`: accessible multi-select cards or checkboxes with one conditional content box per selected factor.
3. `Review Experiment`: a compact summary of the assessment configuration and enabled factors.

Do not use a single-select dropdown because factors are independently combinable. Remove the inactive Save Draft control and replace hard-coded variant/time footer text with values derived from form state.

- [ ] **Step 2: Add prompt-factor controls and validation**

Create `PromptFactorFields.tsx` with these stable factor definitions:

```ts
export const PROMPT_FACTORS = [
  {
    id: 'conceptBridge',
    label: 'Concept Bridge',
    help: 'Connect the assessment topic to concepts or prior knowledge students already know.',
    placeholder: 'Describe the concepts or prior knowledge to connect...',
  },
  {
    id: 'fewShot',
    label: 'Few-shot Examples',
    help: 'Provide complete examples that demonstrate the desired question-and-answer pattern.',
    placeholder: 'Paste one or more representative question-and-answer examples...',
  },
  {
    id: 'referenceContent',
    label: 'Reference Content',
    help: 'Provide notes, excerpts, facts, or source material that the assessment must use.',
    placeholder: 'Paste the source content the assessment should use...',
  },
  {
    id: 'reasoningGuidance',
    label: 'Reasoning Guidance (chain-of-thought condition)',
    help: 'Request a concise rationale or structured solution steps; do not request hidden private model reasoning.',
    placeholder: 'Describe the visible reasoning format, such as key steps or a concise answer rationale...',
  },
] as const
```

Use native checkbox/button semantics, visible focus states, associated labels, help text, and `aria-expanded` on controls that reveal content. Keep typed content in local state when a factor is deselected, but omit that content from the submitted payload.

Validate beside the relevant field:

- Course, topic, and learning objectives are required.
- Question count must be an integer from 1 through 50.
- Estimated student completion time must be an integer from 1 through 480 minutes.
- Every enabled factor must have non-whitespace content.
- Each factor content field is limited to 20,000 characters and shows a live character count.
- Few-shot content must contain at least one non-empty example; display guidance rather than attempting unreliable semantic parsing in the browser.

- [ ] **Step 3: Submit experiment payload**

Use `experimentsApi.create`:

```ts
const experiment = await experimentsApi.create({
  course: form.course.trim(),
  topic: form.topic.trim(),
  learning_objectives: form.learningObjectives.trim(),
  assessment_type: form.assessmentType,
  difficulty: form.difficulty,
  number_of_questions: parseInt(form.numberOfQuestions) || 4,
  estimated_time_minutes: parseInt(form.estimatedTimeMinutes),
  prompt_structure: form.promptStructure,
  factors: {
    concept_bridge: form.conceptBridge,
    few_shot: form.fewShot,
    reference_content: form.referenceContent,
    reasoning_guidance: form.reasoningGuidance,
  },
  factor_inputs: {
    ...(form.conceptBridge && { concept_bridge: form.conceptBridgeContent.trim() }),
    ...(form.fewShot && { few_shot: form.fewShotContent.trim() }),
    ...(form.referenceContent && { reference_content: form.referenceContentText.trim() }),
    ...(form.reasoningGuidance && { reasoning_guidance: form.reasoningGuidanceContent.trim() }),
  },
})
navigate(`/experiments/${experiment.id}/progress`)
```

- [ ] **Step 4: Add review summary and leave-page protection**

Show course, topic, assessment format, difficulty, question count, estimated student completion time, prompt structure, and enabled factor names before submission. Clearly distinguish estimated student completion time from generation time.

Prompt before leaving the page when the form contains unsaved changes. Do not prompt after a successful experiment submission.

- [ ] **Step 5: Rename visible product text**

Use:

```text
Blueprint Lab
New Experiment
Run Experiment
Prompt Design Factors
Estimated student completion time
Reasoning Guidance (chain-of-thought condition)
```

Do not show Forge, RISEN, production pedagogical controls, or PDF as the primary export.

- [ ] **Step 6: Test the streamlined workflow**

Update `frontend/src/App.test.tsx` to verify removed fields are absent; retained fields are present; selecting each factor reveals only its matching content box; enabled empty factors block submission; deselected content is omitted; estimated time validation is inline; the review summary reflects current values; and keyboard users can select factors and run the experiment.

- [ ] **Step 7: Run frontend checks**

Run:

```powershell
cd frontend
npm test -- --run
npm run build
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add frontend/src/pages/InputPanelPage.tsx frontend/src/components/PromptFactorFields.tsx frontend/src/App.test.tsx
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
Also display enabled factor names and the estimated student completion time. Keep full factor content behind an expandable metadata detail so the progress list remains scannable.

- [ ] **Step 4: Update viewer page**

Use `generationsApi.get`, `generationsApi.regenerate`, and `generationsApi.exportDocx`. Show:

```text
Assessment ID
Prompt ID or prompt preview
Experiment Condition
Enabled Prompt Design Factors
Estimated Student Completion Time
Course
Topic
Generated Questions
Solutions
```

The primary export button should call `exportDocx`. PDF can remain hidden or secondary.
The metadata view must expose the exact submitted factor content for reproducibility. Show reasoning guidance as requested visible rationale/steps and never imply that hidden private model reasoning is available.

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

- Spec coverage: The plan covers renaming, planner removal, fixed OpenAI/optional Anthropic structures, independently selected prompt design factors with exact factor content, reasoning guidance as visible rationale or structured steps, estimated student completion time, a single-page accessible input flow, inline validation, a review summary, DOCX primary output, full metadata logging, condition traceability, future rubric scoring, database simplification, retained FastAPI/React/Celery/SSE/persistence/regeneration, and the core abstraction shift to experiment/condition/generation/evaluation.
- Cross-layer requirement: Backend schemas, condition persistence, prompt construction, and metadata export must use `concept_bridge`, `few_shot`, `reference_content`, `reasoning_guidance`, `factor_inputs`, and `estimated_time_minutes` exactly as defined in Task 10. Frontend work must not ship until those API fields are accepted and persisted.
- Known implementation choice: The plan keeps old filenames such as `assessment_worker.py` temporarily to reduce Celery import churn. A later cleanup can rename files after the migration is stable.
- Risk: Existing SQLite data is not migrated. This is acceptable for a forked research platform unless production data must be retained. If retention is required, add an Alembic/data migration task before deleting old models.
- Dependency risk: `python-docx` must be installed before DOCX tests pass.
