# Read-Only Run History Design

## Goal

Restore access to previous assessment runs from the assessment-creation page. Users can open a terminal run by its topic, inspect the evidence saved for that run, redownload its original Word document, and review its LLM and human evaluations without changing any historical data.

The history experience must reuse the established assessment and evaluation presentation while remaining operationally separate from the editable grading workflow. Merely viewing history must not create a human draft, record LLM-disclosure access, reopen an evaluation, regenerate an artifact, or make any other database mutation.

## Scope

This feature includes:

- a Recent Runs button and right-side drawer on the assessment-creation page;
- completed and failed terminal runs identified primarily by the user-entered topic;
- a read-only run-history page for saved assessment evidence;
- read-only question evaluation pages with the existing Previous/Next Assessment navigation;
- redownload of the exact DOCX artifact already persisted for a completed run;
- shared display components between the live workflow and history where doing so does not couple read-only views to mutation behavior.

This feature does not include:

- displaying pending or actively processing runs in the drawer;
- editing, finalizing, reopening, retrying, or creating evaluations from history;
- retrying failed generation from the history view;
- calculating or storing an aggregate run-level grade;
- regenerating missing DOCX artifacts;
- a new document-artifact table or DOCX column.

## Navigation and Run Selection

The assessment-creation page adds a **Recent Runs** button to the top-right header. Activating it opens a right-side drawer over the current page. Opening or closing the drawer preserves every value currently entered in the assessment form.

The drawer lists only terminal runs:

- database statuses `complete` and `complete_with_warnings` use white cards and include explicit Completed text;
- database status `error` uses red cards and includes explicit Failed text;
- pending and active runs remain absent until they become completed or failed.

Color is supplementary rather than the only indication of state. Each card uses the experiment topic entered by the user as its primary label. Run number, terminal status, and date provide supporting context. Completed cards use `completed_at` when available. Failed cards use the latest persisted run timestamp available under the existing schema and do not require a new failure-timestamp column. The list is ordered from most recent to oldest.

The drawer closes through its close button, the Escape key, or an outside click. On narrow screens it becomes a full-width overlay rather than compressing the assessment form.

Selecting a completed card opens:

```text
/runs/{runId}/history
```

Selecting a failed card opens the same route with the failed-state presentation described below.

## Completed Run History Page

The completed run-history page presents the saved run as a sequence of independent accordion sections:

1. **Assessment Details** is collapsed by default.
2. **Actual Prompt** is collapsed by default.
3. **Questions and Solutions** is expanded by default.

The page header contains the topic and run context. A **Download Word DOCX** control appears in the top-right action group. A **Next** control using the project's existing navigation style appears after the Questions and Solutions content and opens the first saved question's read-only evaluation.

### Assessment Details

Assessment Details contains the immutable experiment and condition inputs used for the run:

- course;
- topic;
- ordered learning objectives;
- assessment format;
- difficulty;
- number of questions;
- estimated student completion time;
- cognitive demand;
- additional instructions, when supplied;
- prompt-structure selection;
- each prompt-design factor's enabled or disabled state;
- the saved input for every enabled factor;
- saved reference-PDF filenames, when applicable.

### Actual Prompt

Actual Prompt uses the same accordion visual language as the existing collapsed LLM Evaluation section. It preserves whitespace and line breaks and provides bounded scrolling for unusually long content. A persisted prompt is displayed exactly as saved. If no prompt record or prompt text exists, the section displays **No actual prompt**.

### Questions and Solutions

Questions and Solutions reuse the current assessment rendering for question bodies, answer choices, correct-choice indication, model solutions, content segments, equation references, and standalone equations. Questions remain in their persisted ordinal order. History rendering never alters or repairs stored assessment output.

### DOCX Download

The database already stores the actual DOCX bytes in the one-to-one `document_artifacts` record for a run, along with the filename, media type, SHA-256 content hash, and creation timestamp. History download uses the existing artifact response and returns those saved bytes. It must not rebuild the document from current assessment data.

Completed legacy runs that lack an artifact show **Word document unavailable**. History does not silently regenerate the missing evidence.

## Failed Run History Page

A failed run deliberately exposes a smaller interface:

- **Assessment Details** is expanded by default;
- **Actual Prompt** is available and displays the persisted prompt or **No actual prompt**.

The following controls and sections are not rendered at all for a failed run:

- Questions and Solutions;
- DOCX download;
- Next or Evaluation navigation;
- evaluation content;
- retry actions.

This rule applies even if partial generation output happens to exist. It gives failed runs one stable, predictable evidence boundary while retaining a saved Actual Prompt when the failure occurred after prompt creation.

## Read-Only Evaluation Page

Completed runs use the route:

```text
/runs/{runId}/history/questions/{questionId}/evaluation
```

The Next control on the run-history page selects the first saved question by ordinal. The evaluation page retains the existing Previous Assessment and Next Assessment controls and their established deterministic question traversal.

The page reuses the existing evaluation information architecture:

1. **LLM Evaluation** is collapsed by default.
2. **Human Evaluation** is expanded and read-only.
3. **Human and LLM Comparison** is collapsed by default.

Read-only presentation replaces editable inputs instead of merely disabling form elements. The page omits Save Draft, Finalize, Reopen, Reset, autosave state, validation controls, retry controls, and every other mutation affordance.

The LLM section presents the saved finalized LLM evaluation for the question. The Human section presents the saved finalized human evaluation for the configured reviewer. The two scores remain separate and are never combined into a run average.

When no finalized human evaluation exists, the Human section displays **Human evaluation not completed**. The LLM evaluation remains available, while comparison is unavailable. Draft and reopened human records are not presented as a completed human grade.

Opening or expanding any history section must not create an evaluation draft or evaluation access event. It also must not alter evaluation timestamps, revisions, or status.

## Architecture

History uses dedicated read-only routes and API contracts but shares focused display components with the live Viewer and Evaluation pages. Shared components accept immutable presentation data and render content. Live workflow containers own editing state and mutation commands; history containers do not receive them.

This boundary prevents a query parameter or disabled button from being the only protection against historical writes. It also avoids duplicating the detailed rubric, mathematical-content, question, and comparison layouts.

The relevant units are:

- **Recent Runs drawer:** loads and presents terminal run summaries and navigates by run ID.
- **Run history service/endpoint:** assembles immutable run evidence from the experiment, condition, run, prompt, assessment, and document-artifact relationships.
- **Completed/failed history container:** enforces status-specific visibility and default accordion state.
- **Read-only evaluation service/endpoint:** selects already finalized question evaluations without calling draft-creation or access-event services.
- **Shared assessment components:** present details, prompt text, and saved questions.
- **Shared evaluation components:** present LLM, finalized human, and comparison data in editable or read-only containers as appropriate.

## API Design

The recent-runs contract will support a terminal-only request or a dedicated terminal-history endpoint. The backend, rather than frontend timing alone, enforces that only completed and failed runs appear.

A read-only history-detail endpoint returns:

- run ID, experiment ID, condition ID, run number, database status, and available run timestamps;
- all Assessment Details fields;
- prompt-design factor configuration and saved inputs;
- persisted Actual Prompt or `null`;
- questions, solutions, and ordered question IDs for completed runs;
- DOCX artifact availability and saved filename;
- evaluation navigation availability.

For failed runs, the response does not expose assessment-output or evaluation-navigation payloads to the frontend, even if partial records exist.

A read-only question-evaluation endpoint returns:

- run, assessment, and question identity;
- immutable question content;
- the finalized LLM evaluation;
- the configured reviewer's finalized human evaluation or `null`;
- comparison data only when both finalized evaluations exist;
- previous and next question IDs;
- the run-history return path.

These endpoints use query-only selection paths. They do not reuse an endpoint whose GET handling creates a human draft or records disclosure access.

## Data and Migration Impact

No database schema migration is required for DOCX storage. `document_artifacts.content` is a binary column containing the generated file, and the artifact has an existing unique association with its run.

No run-level grade column is added. LLM and human scores remain normalized per question and evaluation type. History reads finalized evaluation records from the existing evaluation tables.

The implementation may add response schemas and query helpers, but it must not duplicate already persisted prompt, assessment, evaluation, or artifact evidence into a new history snapshot.

## Loading and Error States

The drawer provides loading, empty, and retryable error states. A load failure does not close the drawer or clear the assessment form.

History pages provide inline retry for recoverable retrieval failures. A missing prompt is a valid data state rendered as **No actual prompt**, not a page error. A missing artifact on an otherwise completed legacy run is rendered as **Word document unavailable** and does not trigger regeneration.

If a requested run or question does not exist, the page presents a not-found state with navigation back to the assessment-creation page or parent run history. If a user directly requests evaluation history for a failed run, the backend rejects the request and the frontend returns to that run's limited history view.

## Accessibility and Responsive Behavior

- The drawer has an accessible name, traps focus while open, restores focus to the Recent Runs button when closed, and supports Escape dismissal.
- Status is expressed in text as well as color.
- Accordion triggers are native buttons with `aria-expanded` and associated panel IDs.
- Hidden failed-run functionality is absent from the accessibility tree, not rendered as disabled controls.
- Long prompts are keyboard-scrollable.
- Previous, Next, close, and download controls retain visible focus treatment.
- On narrow screens the drawer becomes a full-width overlay, header actions wrap, and evaluation content follows the existing responsive layout.

## Testing Strategy

### Backend

Tests will verify:

- terminal history includes completed and failed runs and excludes all active states;
- run cards receive the correct topic, run number, status, and terminal timestamp;
- completed history returns every approved assessment-detail field and prompt-factor input;
- Actual Prompt returns exact saved text or `null`;
- completed history returns immutable questions, solutions, saved order, and artifact metadata;
- failed history omits questions, solutions, artifact actions, and evaluation navigation;
- evaluation history returns finalized LLM and configured-reviewer human records separately;
- an absent finalized human evaluation produces `null` rather than a draft;
- comparison is returned only when both finalized evaluations exist;
- history reads create no evaluation, revision, access-event, or artifact rows and update no timestamps;
- DOCX download returns the exact stored bytes, media type, and filename;
- direct evaluation-history access for a failed run is rejected.

### Frontend

Tests will verify:

- the header button opens and closes the drawer without losing form input;
- the drawer hides active runs and renders completed and failed visual/text states;
- cards use topic as the primary label;
- completed and failed selections navigate to the correct history state;
- completed accordions use the approved default open states;
- failed history renders only expanded Assessment Details and Actual Prompt;
- the Actual Prompt fallback is displayed;
- questions, solutions, mathematical content, and saved order render correctly;
- DOCX download and Next are available only for completed history;
- Next opens the first saved question;
- Previous/Next Assessment navigation works in read-only evaluation history;
- no editing or mutation actions appear;
- no finalized human evaluation produces the approved message and unavailable comparison;
- drawer and accordion keyboard interactions are accessible;
- the drawer and history pages remain usable at narrow widths.

### End to End

An end-to-end scenario will open Recent Runs, select a completed topic, inspect each history section, download and compare the exact stored DOCX artifact, enter the first evaluation, traverse questions with Previous/Next, and confirm that evaluation records remain unchanged. A second scenario will select a failed topic and confirm the limited history interface.

## Success Criteria

The design is successful when a user can return to a terminal run by topic, understand whether it completed or failed, inspect all permitted saved evidence, redownload the original DOCX for a completed run, and review separate finalized LLM and human grades without any historical write or regeneration occurring.
