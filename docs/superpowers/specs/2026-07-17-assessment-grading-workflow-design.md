# Assessment Grading Workflow Design

## Goal

Add automatic LLM rubric evaluation to assessment generation and a human-first grading workflow that preserves evaluator independence, research traceability, immutable generated evidence, and accurate token accounting.

The Assessment Viewer becomes available as soon as generation and validation succeed. LLM evaluation continues asynchronously, and the Viewer receives live run snapshots so its token counter and evaluation status update without a page reload. The Assessment Grading Page becomes available only after the saved LLM evaluation is complete.

## Rubric Contract

Rubric version `2026-07-16` is the immutable scoring contract for both human and LLM evaluations. Each evaluation stores the rubric version and a rubric snapshot so later rubric changes cannot silently reinterpret existing results.

| Criterion | Key | Weight |
| --- | --- | ---: |
| Technical Correctness & Solvability | `technical_correctness` | 30% |
| Course Alignment & Concept Bridge | `course_alignment` | 25% |
| Bloom’s Taxonomy Alignment & Assessment Design | `blooms_alignment` | 10% |
| Clarity, Prompt Alignment & Solution Quality | `clarity_solution` | 25% |
| Materials Science Context & Relevance | `materials_context` | 10% |

Every criterion uses an integer score from 1 through 5. The interface presents the exact rubric descriptions and the exact 1, 3, and 5 anchors. Scores 2 and 4 are described only as intermediate performance between the adjacent anchors, matching the rubric instructions.

The weighted total is calculated out of 100:

```text
technical score × 30 / 5
+ course-alignment score × 25 / 5
+ Bloom’s-alignment score × 10 / 5
+ clarity-and-solution score × 25 / 5
+ materials-context score × 10 / 5
```

Technical Correctness & Solvability is the critical gate. A technical score below 3 produces `FAIL` and forces the overall decision to `Not ready – critical issue`, regardless of the weighted total. Otherwise, the decision thresholds are:

| Weighted total | Overall decision |
| ---: | --- |
| 90–100 | Instructor-ready |
| 80–89.9 | Strong – minor revision |
| 70–79.9 | Usable – moderate revision |
| 60–69.9 | Substantial revision |
| Below 60 | Not ready |

The backend is authoritative for stored calculations. The frontend uses the same pure calculation contract to show immediate feedback while a draft is edited.

## Assessment and Question Identity

The existing `Assessment` remains the immutable provider response for one run. Successful validation creates one `AssessmentQuestion` record for each parsed question, in source order. Each question record contains:

- a database-generated question ID;
- assessment ID and ordinal;
- assessment version `1` for the current immutable run model;
- a canonical content hash covering the question, options, model answer, equations, metadata, and revision options;
- creation timestamp.

Evaluation records reference both the assessment and the stable question row. Existing JSON remains the source evidence and is not modified by evaluation. Regeneration continues to create a new run and assessment, which necessarily creates new question identities and requires new evaluations.

## Generation and Evaluation Pipeline

The persisted progress stages and user-facing labels are:

| Stage | Label |
| --- | --- |
| `preparing_prompt` | Preparing Prompt |
| `generating_assessment` | Generating Assessment |
| `validating_assessment` | Validating Assessment |
| `evaluating_quality` | Evaluating Assessment Quality |
| `saving_results` | Saving Results |
| `complete` | Complete |
| `generation_failed` | Generation Failed |
| `evaluation_failed` | Evaluation Failed |

The worker performs prompt preparation, assessment generation, validation, question persistence, LLM evaluation, result persistence, and artifact creation in that order. The generated assessment is committed before evaluation begins. Evaluation receives the saved question and model answer and may analyze them but cannot rewrite them.

After validation and question persistence, the run sets `viewer_ready_at`. This makes the Assessment Viewer action available even while LLM evaluation continues. The Progress Page continues showing the active evaluation or saving stage and does not falsely label the run complete.

The evaluation stage persists a current progress message and publishes a run snapshot after each message transition:

- Preparing generated assessment for evaluation
- Evaluating technical correctness and solvability
- Evaluating course alignment and concept bridge
- Evaluating Bloom’s taxonomy alignment
- Evaluating clarity and solution quality
- Evaluating materials science relevance
- Calculating weighted score
- Saving LLM evaluation results

The evaluator processes each saved question and validates its structured result against the rubric schema. A run reaches `complete` only after every question has a finalized LLM evaluation and the remaining result artifacts are saved.

If LLM evaluation fails, the run enters `evaluation_failed`, preserves `viewer_ready_at`, and retains every successfully generated question and any completed evaluation records. The user may continue viewing the generated assessment. A retry action evaluates only missing or failed question evaluations and never re-enters prompt preparation, generation, or question validation.

The Assessment Grading Page is unavailable until every question in the selected assessment has a completed LLM evaluation. This guarantees that opening the grading page never initiates evaluation and its collapsed LLM section always has saved read-only content.

## Token Accounting

`ModelCallUsage.stage` adds `evaluation` as an allowed stage. Every evaluator model call records provider-reported input, output, total, cached-content, reasoning, and additional token counts using the existing usage tracking service.

Run aggregates include all prompt-generation, assessment-generation, repair, and evaluation calls. Evaluation retries add their usage rather than replacing earlier attempts. Failed attempts remain in the usage ledger whenever the provider returns usage, preserving actual research cost.

The Progress Page publishes a fresh run snapshot after usage is persisted. The Assessment Viewer subscribes to the same run progress stream while the run is not complete, merges each snapshot into the store, and updates `TokenUsage` automatically. A reviewer who opens the Viewer before evaluation completes initially sees the recorded generation usage and then sees evaluation-stage and total counts update without reloading.

## Evaluation Data Model

The legacy `rubric_results` table remains readable and unchanged. New work uses normalized records.

### `assessment_questions`

- `id`
- `assessment_id`
- `ordinal`
- `assessment_version`
- `content_hash`
- `created_at`

The pair `(assessment_id, ordinal)` and each content hash within an assessment are constrained for deterministic identity.

### `evaluations`

- evaluation ID;
- experiment, condition, run, assessment, and question IDs;
- prompt template, actual prompt, and output IDs captured from generated metadata;
- generation model and version;
- prompt design factors snapshot;
- evaluation type: `llm` or `human`;
- evaluator identity;
- evaluation model and version when applicable;
- rubric version and rubric snapshot;
- weighted score, critical-gate result, overall decision, and instructor readiness;
- highest-priority issue, overall comments, and recommended action;
- status: `draft`, `finalized`, `failed`, or `reopened`;
- created, updated, and finalized timestamps.

Multiple evaluations may reference the same question. No constraint assumes one human reviewer or one LLM evaluator. Services select the relevant current evaluation explicitly by evaluation ID and evaluator identity rather than overwriting another record.

### `evaluation_criteria`

- evaluation ID and criterion key;
- integer score from 1 through 5;
- criterion comment;
- suggested modification;
- selected issue flags;
- LLM strengths, weaknesses, suggested improvements, and suggested modifications.

The pair `(evaluation_id, criterion_key)` is unique. Human fields and LLM evidence share one normalized shape but API schemas expose only the fields appropriate to the evaluation type.

### `evaluation_revisions`

Before a finalized human evaluation is reopened, the service stores an immutable JSON snapshot containing the evaluation header, all criteria, calculated outcomes, reviewer identity, and finalization timestamp. Reopening unlocks the live evaluation as a new revision while preserving the prior finalized state.

### `evaluation_access_events`

Expanding the LLM dropdown writes one idempotent first-open event per human evaluation and may append later opens. Events record reviewer ID, human evaluation ID, LLM evaluation ID, opened timestamp, and whether the first open occurred before human finalization.

## API Design

The new router follows existing assessment IDs while retaining run traceability:

```text
GET  /assessments/{assessment_id}/questions
GET  /assessment-questions/{question_id}/grading-context
POST /assessments/{assessment_id}/evaluations/llm/retry
GET  /assessments/{assessment_id}/evaluations
POST /assessment-questions/{question_id}/evaluations/human
PATCH /evaluations/{evaluation_id}
POST /evaluations/{evaluation_id}/finalize
POST /evaluations/{evaluation_id}/reopen
POST /evaluations/{evaluation_id}/llm-access
GET  /assessment-questions/{question_id}/evaluation-comparison
```

The grading-context response returns the selected question, experiment/run provenance needed by the page, adjacent question IDs, the current reviewer’s human evaluation, and the completed LLM evaluation. It does not expose editable generated content.

The current single-user deployment uses the configured local reviewer identity as the evaluator identity. Service and schema boundaries require an explicit reviewer identity so authentication or researcher selection can replace that source later without changing evaluation ownership rules.

Draft creation is idempotent for the same reviewer, question, and active draft. PATCH requests use the evaluation update timestamp for optimistic concurrency and reject stale edits rather than silently overwriting newer work.

Finalization requires all five criterion scores and recalculates every derived value on the server. Comments, suggestions, flags, highest-priority issue, overall comments, and recommended action remain optional. Reopening requires an explicit endpoint call and creates revision history before unlocking fields.

## Experiment Progress Page

The page renders all six principal stages in order, highlights the active stage, and shows the persisted progress message. Once `viewer_ready_at` is present, it displays **View Assessment** even while evaluation continues.

For `evaluation_failed`, the page shows that generation and validation succeeded, displays the sanitized evaluation error, retains **View Assessment**, and adds **Retry LLM Evaluation**. It does not offer assessment regeneration as part of that retry.

The Progress Page publishes updated run snapshots after evaluation usage is saved. Token presentation remains in the Assessment Viewer, where the existing token counter updates from those snapshots.

## Assessment Viewer

The Viewer accepts runs with `viewer_ready_at`, not only runs whose overall status is `complete`. It displays an evaluation badge with one of:

- Evaluation in progress
- Evaluation complete
- Evaluation failed

The top-right action group contains:

1. **Grade Assessment** as the primary action;
2. **Export Word document** as a secondary action;
3. **Retry run** as the existing lower-emphasis action.

Before LLM evaluation is complete, the primary control is disabled and reads **Evaluation in progress**. For an evaluation failure, it reads **Evaluation unavailable**, and the page offers **Retry LLM Evaluation** separately. Once all LLM evaluations are saved, **Grade Assessment** opens the first question without a finalized human evaluation for the current reviewer, falling back to the first question when all questions already have human records.

If the Viewer becomes available before the Word artifact is saved, **Export Word document** is temporarily disabled and reads **Preparing document**. It becomes available from the same live run snapshots when artifact persistence completes.

The Viewer continues to show all questions for the run. It does not add a separate grading button to every question card; Previous/Next navigation on the grading page provides the sequential review workflow.

The Viewer subscribes to progress snapshots until completion or evaluation failure so the status badge, grading action, and token counter update in place.

## Assessment Grading Page

The route is:

```text
/assessments/{assessmentId}/questions/{questionId}/grade
```

There is no Assessment Summary section or summary metadata card. The page header contains only the question title, evaluation status, **Return to Assessment Viewer**, **Previous Assessment**, and **Next Assessment**. Previous and Next traverse saved questions across the current experiment in deterministic condition, run, and question order.

The content order is:

1. collapsed **View LLM Assessment** bar;
2. expanded **Human Assessment**;
3. collapsed **Compare Human and LLM Results**.

The LLM bar appears before Human Assessment but remains closed by default. A notice asks the reviewer to complete the human assessment before reviewing LLM feedback. The reviewer may open it before finalization, but the system records the access time and pre-finalization state for research analysis.

### Human Assessment

Each rubric dimension is a separate card containing the exact title, description, weight, score guidance, accessible 1–5 selector, multiline reviewer comment, optional suggested modification, and multi-select issue flags:

- Technical error
- Missing information
- Ambiguous wording
- Incorrect model answer
- Course misalignment
- Bloom’s level mismatch
- Weak materials science context
- Incomplete solution
- Prompt instruction not followed
- Other

The summary shows the automatically calculated weighted score, critical gate, overall quality decision, and instructor readiness. The reviewer may enter the highest-priority issue, overall comments, and one recommended action:

- Accept without revision
- Accept with minor revision
- Revise before use
- Major revision required
- Reject assessment

The page creates or loads the current reviewer’s draft and records the human assessment start time. Completed fields save on blur, and dirty drafts save periodically. **Save Draft** forces an immediate save. **Reset Unsaved Changes** restores the latest server representation. Route changes and browser exits warn while unsaved edits exist.

**Finalize Human Assessment** remains disabled until all five scores are present. Finalization locks scores and comments, records reviewer and completion timestamp, and enables comparison. **Reopen Evaluation** is the only way to unlock a finalized evaluation and preserves the finalized snapshot first.

### LLM Assessment

The read-only panel is labeled **LLM-Generated Evaluation** and displays evaluation model, version, timestamp, weighted score, gate result, overall decision, instructor readiness, and per-criterion evidence. Each criterion includes score, weight, justification, strengths, weaknesses, suggested improvements, and suggested modifications. The footer shows major strengths, major weaknesses, highest-priority revision, and recommended instructor action.

Expanding and collapsing this panel never starts a model call or changes evaluation content.

### Human and LLM Comparison

The comparison control is disabled until the human evaluation is finalized. It displays per-criterion human score, LLM score, signed difference, and a neutral indicator:

- Agreement for a difference of 0;
- Minor difference for an absolute difference of 1;
- Significant difference for an absolute difference of 2 or more.

It also calculates mean absolute score difference, exact agreement rate, agreement within one point, largest disagreement, both weighted totals, and overall-decision difference. Explanatory copy states that agreement is not evidence that either evaluator is correct.

## Accessibility and Responsive Behavior

All accordions use native buttons with `aria-expanded` and associated panel IDs. Score choices use a labeled radio group, issue flags use native checkbox semantics, status is conveyed by text in addition to color, and validation errors are associated with their controls.

Desktop and laptop layouts keep rubric cards readable without hiding actions. At narrower widths, header actions wrap, metadata pairs become one column, score choices remain keyboard reachable, and the sticky draft action row becomes an ordinary stacked action group when it would obscure content.

## Error Handling and Concurrency

- Generation or validation failure creates no evaluation and does not expose the Viewer.
- Evaluation failure preserves the assessment and Viewer access but prevents grading access.
- Retrying evaluation targets only failed or missing LLM records.
- Invalid evaluator JSON is treated as evaluation failure and never changes question content.
- Stale human PATCH requests receive a conflict response containing the current server version.
- A failed autosave keeps the draft dirty, presents a nonblocking error, and retries on the next save trigger.
- Finalization is transactional across criteria, calculated values, status, and timestamps.
- Duplicate finalization requests are idempotent for an already finalized evaluation.
- Navigation never silently discards dirty local changes.

## Testing Strategy

Backend tests cover:

- migration creation, constraints, and preservation of legacy rubric results;
- deterministic question persistence and content hashing;
- exact scoring thresholds and critical-gate precedence;
- LLM schema validation and read-only assessment input;
- viewer readiness before evaluation completion;
- successful automatic evaluation and final completion;
- evaluation failure preservation and evaluation-only retry;
- evaluation token accounting, including retries and failed attempts with usage;
- multiple reviewers and multiple evaluator records without overwrites;
- draft concurrency, finalization, reopening, and revision snapshots;
- LLM access-event auditing;
- comparison metrics and availability rules;
- API authorization/ownership boundaries through the current reviewer identity.

Frontend unit and integration tests cover:

- six-stage progress rendering and evaluation messages;
- early View Assessment availability;
- live token and evaluation-status refresh in the Viewer;
- Grade Assessment placement and enabled/disabled states;
- absence of an Assessment Summary section;
- LLM-before-human ordering with both secondary sections collapsed initially;
- complete rubric cards, score limits, flags, autosave, dirty resets, and navigation warnings;
- finalization requirements and locking;
- access-event recording when LLM content is opened;
- comparison enablement and metrics;
- keyboard behavior and automated accessibility checks.

End-to-end coverage generates a saved assessment, opens the Viewer while evaluation is still running, observes token totals update, enters grading after evaluation completes, saves and finalizes a human review, and inspects the comparison without modifying either source evaluation.

## Compatibility and Documentation

Existing completed runs without LLM evaluations remain viewable. Their grading action reports that evaluation is unavailable; evaluation may be explicitly backfilled through the retry endpoint without regenerating the assessment. Existing assessment JSON, prompts, output hashes, DOCX artifacts, and legacy rubric results are never rewritten.

README and lifecycle documentation describe the new viewer-ready boundary, final run-completion boundary, evaluation retry behavior, rubric version, and inclusion of evaluator tokens in run totals.
