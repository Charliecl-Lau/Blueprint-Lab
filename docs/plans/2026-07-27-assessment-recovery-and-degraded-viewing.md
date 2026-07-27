# Assessment Recovery and Degraded Viewing Execution Plan

**Date:** 2026-07-27
**Status:** Approved design; ready for implementation
**Primary production example:** Experiment 21, run 22, assessment 11

## Outcome

Recover structurally usable assessment responses instead of hiding them after the
LLM repair limit is reached.

The implementation has two independent recovery layers:

1. Strengthen the Actual Prompt so component-indexed variable families use
   explicit canonical identifiers such as `x_a`, `x_b`, `y_a`, and `y_b`, and
   require every occurrence in prose to use an equation reference.
2. Deterministically repair safe, mechanically identifiable equation-reference
   defects such as the raw `x_B` and `x_A` tokens that caused experiment 21 to
   fail.
3. When strict validation still fails but the response is valid JSON containing
   the requested questions, persist it as a viewable assessment with warnings.
   Keep export and evaluation locked until the user explicitly accepts the
   defects.

Malformed JSON, missing question arrays, incorrect question counts, or question
objects that cannot be rendered safely remain terminal errors.

## State Model

### Run states

Extend the run status contract with one terminal state:

- `complete`: strict validation passed.
- `complete_with_warnings`: the assessment is structurally renderable but has
  unresolved validation issues.
- `error`: the response cannot be safely parsed or rendered.

`complete_with_warnings` must be treated as terminal by progress polling and SSE.
It must make the Assessment Viewer available, but it must not imply that the
assessment is instructor-ready.

### Assessment validation fields

Add the following fields to `assessments`:

- `validation_status`: `valid`, `warning`, or `invalid`.
- `validation_issues`: ordered JSON array of structured issues.
- `recovery_actions`: ordered JSON array describing deterministic changes.
- `parsed_json_hash`: SHA-256 of canonical `parsed_json`, nullable when parsing
  failed.
- `defects_accepted_at`: nullable timestamp.
- `defects_accepted_by`: nullable reviewer identity.

Keep `output_hash` as the hash of the exact provider response. Do not recompute it
from a recovered or normalized object. `parsed_json_hash` separately identifies
the data rendered to the user.

Backfill existing assessments as follows:

- `parsed_json IS NOT NULL` -> `validation_status='valid'`, empty issues/actions,
  and a canonical parsed JSON hash.
- `parsed_json IS NULL` -> `validation_status='invalid'`, empty issues/actions,
  and no parsed JSON hash.

Do not automatically alter old failed runs during migration. Recovery must be an
explicit, auditable operation.

## Structured Validation Issues

Replace string-only equation failures with structured internal issues while
preserving readable Pydantic/API error messages.

Each issue should contain:

```json
{
  "code": "raw_math_token",
  "question_ordinal": 0,
  "field_path": "body",
  "excerpt": "x_B",
  "message": "Mathematical content must use an equation reference.",
  "recoverable": true
}
```

At minimum, support codes for:

- raw subscript or superscript token;
- raw equality or mathematical expression;
- fragmented equation reference;
- unknown equation label;
- location mismatch;
- label shared between question and solution;
- unreferenced equation;
- invalid or missing question structure;
- incorrect question count.

Keep issue ordering deterministic: question ordinal, field path, and source
position.

## Actual Prompt Variable Contract

Update `docs/actual_prompt_template.md`, generated structure-system prompts, and
assessment-repair instructions so prevention and recovery enforce the same
variable convention.

### Canonical component-indexed variables

When a problem uses more than one component or member of a variable family:

- do not use ambiguous bare variables such as `x` or `y`;
- use explicit lowercase ASCII component subscripts;
- use `x_a` and `x_b` for the `x` family;
- use `y_a` and `y_b` for the `y` family;
- extend the same rule consistently for additional families or components, for
  example `z_a`, `z_b`, and `x_c`;
- define what each base symbol and component subscript represents.

The canonical form is lowercase, including the component subscript. For example,
prefer `x_a` over `x_A`, `x1`, or a bare `x` when components A and B are both
present.

### Output-format requirements

The Actual Prompt's output-format example and constraints must demonstrate that
component-indexed variables live inside `equations[]` entries and never appear
as raw mathematical text in `body`, option bodies, or `model_answer`.

Required pattern:

```json
{
  "body": "Compare [[EQ:x_a_symbol]] and [[EQ:x_b_symbol]].",
  "equations": [
    {
      "label": "x_a_symbol",
      "expression": "x_a",
      "location": "question"
    },
    {
      "label": "x_b_symbol",
      "expression": "x_b",
      "location": "question"
    }
  ]
}
```

The prompt must explicitly require the model to scan `body`, every option body,
and `model_answer` before returning JSON. Every standalone mathematical
identifier must be replaced with an `[[EQ:label]]` reference, including short
component variables such as `x_a`, `x_b`, `y_a`, and `y_b`.

The schema and repair prompts must use the same examples and terminology so the
generation request, provider structured-output contract, Pydantic validation,
and repair request do not give conflicting instructions.

## Deterministic Equation Recovery

Create a focused backend service, for example
`backend/services/assessment_recovery.py`.

The service accepts the decoded provider JSON and returns:

```python
RecoveryResult(
    parsed_json=...,
    actions=[...],
    remaining_issues=[...],
    strictly_valid=True | False,
    structurally_renderable=True | False,
)
```

### Safe automatic transformation

Systematically scan every textual assessment field:

- question `body`;
- every answer-option `body`;
- `model_answer`.

Ignore spans already inside `[[EQ:...]]` references. Initially auto-repair only
standalone subscript/superscript symbol tokens that are outside those
references. Examples include `x_a`, `x_b`, `y_a`, `y_b`, legacy `x_A`/`x_B`,
`G^E`, and `mu_A`.

Normalize legacy component-subscript casing when the identity is already
explicit: for example, `x_A` becomes canonical `x_a`. Do not infer a component
identity for an ambiguous bare `x` or `y`. Report an unresolved structured issue
instead, because automatically choosing `_a` or `_b` could change the
mathematical meaning.

For each token:

1. Identify its exact field and text span.
2. Normalize an explicitly identified component variable to canonical lowercase
   form without changing its component identity.
3. Reuse an existing equation entry only when canonical expression and location
   match.
4. Otherwise create a collision-safe ASCII label such as
   `auto_q1_body_x_b_1`.
5. Add an equation entry containing the canonical token and the correct
   `question` or `solution` location.
6. Replace only that exact span with `[[EQ:<label>]]`.
7. Record the original token, canonical token, field path, text span, label,
   location, and action type.

Do not automatically extract ambiguous multi-token equations, prose containing
operators, or fragmented derivations in the first release. Report those as
remaining issues and use degraded viewing.

### Recovery invariants

- Never modify text inside an existing equation reference.
- Never change numeric values or mathematical meaning.
- Never guess whether an ambiguous bare variable belongs to component A, B, or
  another component.
- Never delete an existing equation entry.
- Never reuse a label across question and solution locations.
- Label generation must be deterministic and collision-safe.
- Applying recovery twice must produce the same parsed JSON and no new actions.
- Strict validation must run again after recovery.

Experiment 21 should become a regression fixture: its raw `x_B` in question 1
and raw `x_A` in the model answer should be converted into equation references
and the recovered result should pass strict validation.

## Worker Data Flow

Refactor the terminal part of `run_generation_pipeline` into a shared
finalization function used by both new generations and recovery of existing
runs.

After the normal LLM repair loop:

1. Attempt strict validation.
2. If strict validation succeeds:
   - save normalized `parsed_json`;
   - set assessment validation status to `valid`;
   - calculate `parsed_json_hash`;
   - persist assessment-question identities;
   - create the DOCX artifact;
   - set the run to `complete`;
   - queue LLM evaluation.
3. If strict validation fails, decode the raw response as JSON and call the
   deterministic recovery service.
4. If deterministic recovery passes strict validation, follow the normal
   `complete` path and store its recovery actions.
5. If strict validation still fails but the object is structurally renderable:
   - save the recovered candidate as `parsed_json`;
   - save its hash, recovery actions, and remaining issues;
   - persist assessment-question identities;
   - set `viewer_ready_at`;
   - set the run to `complete_with_warnings`;
   - do not create an artifact;
   - do not queue LLM evaluation.
6. If it is not structurally renderable:
   - keep `parsed_json` null;
   - store structured validation issues when available;
   - retain the existing `assessment_parse_error` behavior.

The raw provider response and its `output_hash` remain unchanged through
deterministic recovery.

## Existing-Run Recovery

Add:

```text
POST /runs/{run_id}/recover-assessment
```

Eligibility:

- run status is `error`;
- `error_type` is `assessment_parse_error`;
- an assessment and raw response exist;
- no valid parsed assessment or artifact exists.

Behavior:

- lock the run and assessment;
- apply the same deterministic recovery/finalization path used by the worker;
- make no provider call;
- record a recovery action with timestamp and recovery implementation version;
- return the updated run detail;
- be idempotent once the run is `complete` or `complete_with_warnings`.

After deployment, invoke this endpoint for run 22. Confirm that experiment 21
becomes either strictly complete after the `x_B`/`x_A` cleanup or, if additional
issues remain, viewable with warnings.

## User Acceptance

Add:

```text
POST /runs/{run_id}/accept-assessment-defects
```

The endpoint is valid only when:

- the run is `complete_with_warnings`;
- `parsed_json` exists;
- validation issues remain;
- defects have not already been accepted.

On acceptance:

1. Lock the run and assessment.
2. Record `defects_accepted_at` and the configured reviewer identity.
3. Generate the DOCX artifact from the accepted parsed assessment.
4. Commit the artifact and acceptance together.
5. Queue LLM evaluation after commit.
6. Keep the run status `complete_with_warnings`; acceptance does not make the
   response strictly valid.

The endpoint is idempotent after successful acceptance.

Update evaluation and grading eligibility rules so they allow:

- `run.status == 'complete'`; or
- `run.status == 'complete_with_warnings'` and
  `assessment.defects_accepted_at IS NOT NULL`.

## API Contract

Extend run detail with:

```json
{
  "viewer_available": true,
  "assessment_validation": {
    "status": "warning",
    "issues": [],
    "recovery_actions": [],
    "parsed_json_hash": "...",
    "defects_accepted_at": null,
    "defects_accepted_by": null,
    "acceptance_required": true
  }
}
```

Rules:

- `viewer_available` is true for `complete`, `complete_with_warnings`, and
  legacy completed runs with parsed data.
- `grading_available` remains false for unaccepted warning assessments.
- `artifact_available` remains false until warning defects are accepted and the
  artifact is generated.
- Raw response retrieval remains opt-in.
- Recent-run and progress responses must include the new status.

## Frontend Behavior

### Progress and recent runs

- Add the label `Completed with warnings`.
- Treat the state as terminal and close SSE.
- Show `View Assessment` for the warning state.
- Use an amber status treatment distinct from green success and red failure.

### Assessment Viewer

For an unaccepted warning assessment:

- render the recovered questions normally;
- show a persistent warning banner above the assessment;
- list issues grouped by question and field;
- distinguish automatically repaired issues from unresolved issues;
- disable Word export and grading;
- offer `Accept assessment with defects`;
- retain the existing `Retry run` action as the option to generate a clean new
  immutable run.

The acceptance confirmation must state that:

- known defects will remain recorded;
- the assessment will remain labeled as completed with warnings;
- acceptance enables export and automated evaluation;
- a new retry is preferable when content correctness is uncertain.

After acceptance, refresh the run. Keep the warning banner visible, display the
acceptance timestamp, and enable export when artifact creation succeeds.

Do not introduce a misleading "repair succeeded" message when unresolved issues
remain.

## Database Migration

Create a new Alembic revision after the current head.

The migration must:

1. Add `complete_with_warnings` to the run status check constraint.
2. Add assessment validation, hash, recovery, and acceptance columns.
3. Backfill existing assessments deterministically.
4. Add check constraints tying acceptance to warning status where practical.
5. Preserve every raw response, output hash, prompt, artifact, evaluation, and
   usage record.
6. Provide a downgrade that removes only the new metadata after converting
   warning runs back to `error`; never delete assessment evidence.

Also reconcile the pre-existing `runs.generated_json` model/migration drift
before deploying this migration. The migration history says the column was
removed, while current runtime models still reference it. Choose
`assessments.parsed_json` as the canonical field and remove runtime dependence
on `runs.generated_json` in this work.

## Test-Driven Execution Order

### Phase 1: Structured issue extraction

Add failing tests in `backend/tests/test_assessment_schema.py` and a new
`backend/tests/test_assessment_recovery.py` for:

- exact issue paths for `x_B` and `x_A`;
- canonical `x_a`, `x_b`, `y_a`, and `y_b` recognition;
- ambiguous bare `x` and `y` being reported rather than guessed;
- ignoring tokens already inside equation references;
- scanning option bodies in addition to question and solution text;
- question versus solution location;
- deterministic issue ordering;
- malformed JSON and structurally unsafe responses.

Implement structured issue extraction without changing existing successful
validation behavior.

### Phase 2: Deterministic symbol recovery

Add failing tests for:

- experiment 21's question 1;
- normalization of legacy `x_A`/`x_B` to `x_a`/`x_b`;
- extraction of `x_a`, `x_b`, `y_a`, and `y_b` across all textual fields;
- label collision handling;
- reuse of a matching existing equation;
- multiple occurrences;
- idempotence;
- preservation of question content and numeric values;
- unresolved complex expressions remaining warnings.

Implement the smallest safe symbol-only recovery service.

Add prompt-contract tests in `backend/tests/test_actual_prompt.py` that verify:

- the Actual Prompt requires canonical component-indexed variable names;
- the output-format example uses equation references rather than raw `x_a`,
  `x_b`, `y_a`, or `y_b` in prose;
- generation and repair instructions require a complete pre-return field scan;
- OpenAI and Anthropic prompt paths communicate the same convention;
- unresolved template placeholders are not introduced.

### Phase 3: Persistence and migration

Add model and PostgreSQL migration tests for:

- the new run status;
- validation-status constraints;
- existing-row backfill;
- raw output hash preservation;
- parsed JSON hash calculation;
- lossless downgrade behavior.

Update SQLAlchemy models and API schemas only after the failing tests establish
the contract.

### Phase 4: Worker recovery paths

Add worker tests covering:

1. strict success without recovery;
2. LLM repair exhaustion followed by deterministic success;
3. renderable response with unresolved issues becoming
   `complete_with_warnings`;
4. malformed response remaining `error`;
5. no artifact/evaluation before acceptance;
6. model-call and token accounting remaining unchanged by deterministic
   recovery.

Refactor worker finalization and implement the shared recovery path.

### Phase 5: Recovery and acceptance APIs

Add API/service tests for:

- recovery eligibility and idempotence;
- recovery without a provider call;
- concurrent recovery protection;
- acceptance eligibility and idempotence;
- atomic artifact creation and acceptance;
- evaluation dispatch only after acceptance;
- run detail serialization and access gating.

### Phase 6: Frontend

Update TypeScript status unions, run APIs, state handling, and viewer UI.

Add component tests for:

- terminal warning progress state;
- View Assessment availability;
- grouped warning details;
- locked export and grading;
- acceptance confirmation and refresh;
- accepted warning state;
- retry-run availability.

### Phase 7: End-to-end verification

Add an end-to-end fixture that reproduces experiment 21:

- initial and three LLM repair outputs retain raw `x_B`/`x_A`;
- deterministic recovery repairs the symbols;
- the Viewer receives the recovered four-question assessment;
- output hash still identifies the provider response;
- recovery actions identify the two replacements.

Add a second fixture with an ambiguous unresolved expression to verify warning,
acceptance, artifact creation, and evaluation gating.

Run:

```powershell
python -m pytest backend/tests/test_assessment_schema.py backend/tests/test_assessment_recovery.py -v
python -m pytest backend/tests/test_worker.py backend/tests/test_api_runs.py -v
python -m pytest backend/tests/integration -v
python -m pytest backend/tests -v
Set-Location frontend
npm test -- --run
npm run lint
npm run build
```

Run PostgreSQL integration tests with `TEST_POSTGRES_DATABASE_URL` configured.
Run `python -m alembic check` against a migrated disposable PostgreSQL database.

## Deployment and Production Verification

1. Back up the Railway PostgreSQL database.
2. Deploy the database migration before application code that emits the new
   status.
3. Deploy API and worker from the same commit.
4. Deploy the frontend after the API reports the new contract.
5. Confirm API and worker share identical model/settings configuration.
6. Invoke `POST /runs/22/recover-assessment`.
7. Verify experiment 21 retains assessment 11 and the original raw output hash.
8. Verify its parsed assessment contains four questions.
9. Verify recovery actions include the question 1 `x_B` and `x_A` replacements.
10. Verify the run is either `complete` or `complete_with_warnings`, never
    silently green when issues remain.
11. If warnings remain, verify the Viewer works while export and grading stay
    locked until acceptance.
12. Confirm experiment 23 and other existing successful runs are unchanged.

## Suggested Commit Sequence

Each commit must include a paragraph body explaining what changed and why, and
must not include co-author attribution.

1. `Add structured assessment validation issues`
2. `Require canonical component variables in assessment prompts`
3. `Add deterministic equation symbol recovery`
4. `Persist assessment validation and acceptance state`
5. `Recover renderable assessments after repair exhaustion`
6. `Add degraded assessment recovery and acceptance APIs`
7. `Show completed assessments with validation warnings`
8. `Verify degraded assessment recovery end to end`

## Completion Criteria

- Experiment 21 can be recovered without regenerating or losing its raw
  response.
- New prompts require canonical `x_a`, `x_b`, `y_a`, and `y_b` component
  variables and equation references in every prose field.
- Recovery systematically scans question bodies, answer options, and model
  answers without guessing ambiguous component identities.
- Safe raw symbol defects are repaired deterministically.
- Renderable outputs remain visible after repair exhaustion.
- Unresolved defects are explicit and auditable.
- Unaccepted degraded assessments cannot be exported or graded.
- Acceptance is explicit, timestamped, and does not erase warning status.
- Malformed or structurally unsafe responses still fail.
- Existing successful runs and evaluations remain unchanged.
- Migration, backend, frontend, and end-to-end tests pass.
