# Main Workflow With Background Assessment Evaluation

## Goal

Restore the assessment generation and progress experience from the `main` branch while retaining the assessment-grading feature as an independent background workflow.

The primary run finishes when the assessment and its document artifact are generated, validated, and saved. At that point the existing main-style progress page shows **View Assessment**. LLM evaluation starts separately and must not delay, reopen, or fail the completed generation run.

## User Experience

The progress page keeps the structure and behavior from `main`. It displays the current generation status and does not display a validation timeline, evaluation stages, evaluation failure, evaluation retry, or grading state.

The visible sequence is:

1. The user submits an experiment.
2. The main workflow generates and saves the assessment and document.
3. The run becomes complete and the progress page shows **View Assessment**.
4. The user may enter the Viewer immediately.
5. LLM assessment evaluation continues in the background.
6. The Viewer reports evaluation as not started, in progress, complete, or failed. Grading becomes available after the saved LLM evaluation is finalized.

The progress page does not wait for evaluation and does not need to stay open for evaluation to continue.

## Primary Run Lifecycle

Restore the run statuses and meanings from `main`:

- `pending`: the run has been created and queued;
- `prompting`: the generation prompt is being prepared;
- `generating`: the assessment model is generating questions;
- `documenting`: the validated assessment and document artifact are being saved;
- `complete`: the assessment, normalized questions, and document artifact are available;
- `error`: assessment generation, parsing, validation, persistence, or document creation failed.

The database status constraint, backend schemas, recent-run handling, progress snapshots, frontend types, status labels, and terminal-state logic use this primary lifecycle. Existing branch-only run states such as `validating_assessment`, `evaluating_quality`, `saving_results`, `generation_failed`, and `evaluation_failed` are mapped back to the main lifecycle by migration.

Assessment parsing and validation remain required, but they are implementation work inside `generating` or `documenting`; they are not new user-facing workflow stages.

## Generation Worker Boundary

The assessment generation worker owns all work required to make the main run complete:

1. build or load the prompt;
2. call the assessment-generation model;
3. validate and parse the response;
4. save the assessment and normalized assessment questions;
5. build and save the DOCX artifact;
6. update model metadata and generation token usage;
7. commit the run as `complete` with `completed_at`;
8. publish the terminal run snapshot;
9. enqueue background LLM evaluation after the completion commit.

The completion commit occurs before evaluation is dispatched. A broker or evaluation failure therefore cannot roll back or change a valid generated assessment.

## Independent Evaluation Lifecycle

Evaluation state is represented by normalized LLM `Evaluation` records, not by `Run.status`.

The background evaluation worker:

- loads the completed run and saved assessment questions;
- creates or resumes the LLM evaluation attempt for each question;
- records evaluation model metadata, criterion results, rubric provenance, and evaluation token usage;
- finalizes successful evaluations;
- records failed evaluation attempts with `status="failed"`;
- publishes evaluation updates for Viewer and Grading consumers;
- never changes the primary run status, primary progress message, or generation completion time;
- remains idempotent by skipping already finalized evaluations for the same question, model identity, and rubric version.

The aggregate evaluation status is derived from LLM evaluation records:

- `not_started`: no LLM evaluation attempt exists;
- `in_progress`: at least one attempt is draft or reopened and no terminal failure governs the current attempt;
- `complete`: every saved question has a finalized LLM evaluation for the active rubric and evaluator identity;
- `failed`: the current evaluation attempt failed before all questions were finalized.

## Viewer and Grading

The Assessment Viewer remains available whenever the main run is `complete`. It displays generated content independently of evaluation availability.

The Viewer shows the background evaluation status and refreshes it without relying on the generation progress stream. The **Grade Assessment** action remains disabled until the relevant LLM evaluation is finalized. Completed LLM results and the human evaluation workflow continue to use the normalized evaluation APIs and grading page already developed in this branch.

If evaluation is not started or failed, the Viewer exposes a separate LLM evaluation retry action. Retrying evaluation does not create a new generation run and does not alter the completed run status.

## Error Handling

Generation errors retain the main behavior: the run becomes `error`, the progress page shows the generation error, and the assessment action remains unavailable.

Evaluation errors are isolated:

- the run remains `complete`;
- the Viewer continues to display the assessment;
- the evaluation status becomes `failed`;
- grading remains unavailable until a retry finalizes the LLM evaluation;
- a retry creates or resumes an evaluation attempt without regenerating the assessment.

If evaluation dispatch fails after generation completion, the run remains complete and evaluation remains `not_started`. The Viewer retry action provides recovery.

## Migration and Compatibility

The migration restores the main run-status constraint and maps existing records without deleting assessment or evaluation evidence:

- `preparing_prompt` to `pending`;
- `generating_assessment` to `generating`;
- `validating_assessment` to `generating`;
- `evaluating_quality` to `complete` only when both the saved assessment and document artifact exist, otherwise `error`;
- `saving_results` to `complete` only when both the saved assessment and document artifact exist, otherwise `error`;
- `generation_failed` to `error`;
- `evaluation_failed` to `complete` only when both the saved assessment and document artifact exist, otherwise `error`.

Existing finalized and failed evaluation records remain unchanged. Existing assessment questions, human evaluations, LLM evaluations, usage records, and access events remain linked to their original run and assessment provenance.

## Testing

Backend lifecycle tests must prove that:

- new runs use the main status vocabulary;
- a valid assessment and DOCX are persisted before the run becomes complete;
- the completion commit and event occur before evaluation dispatch;
- evaluation activity and failure never change a completed run status;
- evaluation status is derived from normalized records;
- evaluation retry does not regenerate the assessment;
- migration mappings preserve assessment and evaluation records.

Frontend tests must prove that:

- the progress page matches the main layout and status behavior;
- **View Assessment** appears when the generation run is complete;
- no evaluation stages or evaluation retry controls appear on the progress page;
- the Viewer remains usable while evaluation is pending or failed;
- grading unlocks only after LLM evaluation finalization;
- the Viewer can retry a not-started or failed evaluation.

An end-to-end lifecycle test must cover generation completion, immediate Viewer access, background evaluation completion, and grading availability as separate observable transitions.

## Out of Scope

This change does not redesign the main progress page, change the assessment generation prompt, regenerate historical assessments, remove normalized grading data, or merge the worktree into `main`. It changes the worktree so its primary workflow behaves like `main` with background evaluation added.
