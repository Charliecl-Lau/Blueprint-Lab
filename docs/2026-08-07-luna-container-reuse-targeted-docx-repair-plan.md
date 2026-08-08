# Luna Container Reuse and Targeted DOCX Repair Plan

## Objective

Change the `luna_direct` DOCX pipeline so one generation cycle owns one OpenAI
Code Interpreter container. The initial generation and all bounded repair calls
reuse that container and its named files. Each repair receives structured,
label-based verifier findings and modifies only the responsible generator code
or DOCX region, while the application still verifies the complete resulting
DOCX after every attempt.

Persist every attempt's sanitized verification evidence and record the exact
number of repairs executed for successful and failed generation cycles.

## Required invariants

- A DOCX cycle creates at most one OpenAI container.
- The container is deleted only after the complete cycle succeeds, fails, or
  raises an unrecoverable error.
- The initial call must save `/mnt/data/builder.py`,
  `/mnt/data/assessment.json`, and `/mnt/data/assessment.docx`.
- Repair calls reuse the same `container_id`; they do not resend source code or
  canonical JSON while that container remains active.
- The application persists necessary evidence locally and never depends on the
  ephemeral container as the system of record.
- Repairs are bounded by `DOCX_TOOL_MAX_REVISIONS`.
- A targeted repair is followed by full package, content, equation, metadata,
  and security verification.
- Non-repairable package/security findings stop the cycle immediately.
- Canonical assessment content remains immutable throughout DOCX repair.
- Provider prompts receive only safe issue codes and bounded sanitized
  evidence, never raw service logs, credentials, or database content.

## Data model

Add `LunaDocxSession` (`luna_docx_sessions`) as the durable record for one DOCX
generation or explicit rewrite cycle:

- `id`, `run_id`, `source_assessment_id`, and `cycle_number`
- `status`: `creating`, `authoring`, `validating`, `repairing`, `succeeded`, or
  `failed`
- `outcome`: nullable until terminal, then `succeeded` or `failed`
- `container_id`: nullable provider identifier for diagnostics
- `maximum_repairs`: configured repair limit captured at cycle creation
- `repair_count`: number of repair calls actually executed; zero for a
  successful or failed initial attempt with no repair
- `attempt_count`: total provider attempts, always `repair_count + 1` after the
  initial call starts
- `final_issue_codes`: deduplicated safe terminal codes
- `final_artifact_sha256`: present only after a verified artifact exists
- `created_at`, `completed_at`, and optional bounded `failure_category`
- unique `(run_id, cycle_number)` and nonnegative/count consistency checks

Add `LunaDocxAttempt` (`luna_docx_attempts`) for every initial or repair call:

- `id`, `session_id`, and one-based `attempt_number`
- `kind`: `initial` or `repair`
- `status`: `requested`, `generated`, `validating`, `succeeded`, or `failed`
- `model_call_usage_id` and `provider_response_id`
- `prompt_hash`, `input_artifact_sha256`, and `output_artifact_sha256`
- `issue_codes`: deduplicated safe verifier codes
- `validation_report`: structured report containing verifier/tool versions,
  package and manifest hashes, validity, and sanitized issue evidence
- `repair_feedback`: the exact structured safe payload supplied to the next LLM
  call, or an empty object when no repair follows
- timestamps and an optional bounded provider failure code
- unique `(session_id, attempt_number)` and unique non-null usage relationship

Do not store repair counts only on `runs`: a run may have multiple explicit
rewrite cycles. Aggregate successful and failed repair statistics from terminal
`LunaDocxSession` rows. The run API may expose the latest session and cumulative
totals as derived values.

Create an Alembic migration after `20260806_01` and migration tests for all
foreign keys, uniqueness constraints, status checks, count checks, and cascade
behavior. Do not backfill unverifiable historical per-attempt evidence. Existing
Luna model usages may be summarized as legacy/unknown evidence if a backfill is
needed, but must not be presented as exact repair history.

## Structured repair evidence

Extend verifier findings with stable targeting fields while retaining `code`,
`repairable`, and bounded `evidence`:

```json
{
  "code": "native_equation_structure_invalid",
  "repairable": true,
  "target": {
    "equation_label": "eq_17",
    "question_id": "question_3",
    "location": "solution"
  },
  "expected": {
    "placement": "display",
    "constructs": ["fraction", "subscript"]
  },
  "actual": {
    "missing_constructs": ["fraction"]
  }
}
```

Use globally unique equation labels where possible. If label uniqueness is not
guaranteed, use `(question_id, location, equation_label)` as the identity. For
non-equation findings, define stable targets such as metadata field name,
drawing identifier, section name, or header/footer part.

Persist the full sanitized report before making the next provider call. Produce
the repair prompt from the persisted structured report rather than rebuilding
it from `run.error_message`.

## Provider lifecycle refactor

Split `LunaDirectDocxProvider.generate()` into cycle-scoped operations:

1. `create_session(run_id)` creates a container and uploads canonical JSON once.
2. `author(session, assessment_json)` runs the initial response and requires the
   named builder and DOCX files.
3. `repair(session, feedback)` uses the same container and instructs Luna to
   inspect the existing files, edit only targeted builder functions or marked
   DOCX nodes, rerun/save the artifact, and cite exactly one resulting DOCX.
4. `download_result(session, response)` validates the citation and downloads the
   current DOCX immediately.
5. `close_session(session)` deletes the container idempotently in an outer
   `finally` block after all attempts.

Keep container reuse independent of response conversation state. Passing a
previous response identifier may improve continuity, but file persistence must
come from the explicit shared container ID.

If the container expires or becomes unavailable during repair, fail with a
stable `docx_container_expired` code in the first implementation. Do not
silently start a new container because that would violate the targeted-repair
contract and make attempt evidence ambiguous. A later fallback may rehydrate a
new container from persisted `builder.py`, JSON, and DOCX artifacts.

## Orchestration flow

Refactor `LunaDirectDocumentGenerator.generate()` as follows:

1. Create and commit a `LunaDocxSession` before contacting OpenAI.
2. Create the provider container and store its identifier.
3. Create an initial `LunaDocxAttempt`; call authoring and record model usage.
4. Download the DOCX, calculate its hash, and verify it locally.
5. Persist the complete sanitized verification report on the attempt.
6. If valid, mark the attempt/session successful, set `repair_count` to the
   number of completed repair calls, persist/canonicalize the artifact, and end.
7. If invalid and any finding is non-repairable, mark the attempt/session failed
   immediately without calling Luna again.
8. If invalid and repair capacity remains, persist structured repair feedback,
   increment `repair_count` only when the repair provider call begins, create the
   next attempt, and reuse the same container.
9. If the last repair remains invalid, mark the attempt/session failed and save
   its final issue codes and evidence.
10. Delete the container in the outer `finally`, preserving the database records
    even if cleanup fails. Record cleanup failure as operational evidence, but
    do not replace a successful document outcome with a cleanup failure.

Database commits must occur at attempt boundaries so crashes leave an auditable
partial session. On recovery, do not duplicate an attempt number or model-call
usage. Use the existing rewrite-cycle idempotency key to prevent duplicate
sessions for the same dispatch.

## Repair instructions

The repair prompt must say:

- reuse `/mnt/data/builder.py`, `/mnt/data/assessment.json`, and the existing
  DOCX;
- modify only code or tagged OOXML associated with the supplied targets;
- never alter canonical question, answer, option, equation expression, or
  metadata values;
- save the revised builder and `/mnt/data/assessment.docx`;
- inspect the final OOXML before citing the file;
- report which target labels were changed.

Initially prefer targeted builder-code edits followed by a deterministic full
DOCX rebuild. Permit direct DOCX patching only for operations with durable
bookmarks/content-control tags and dedicated tests. “Targeted repair” limits the
change surface; it does not reduce verification scope.

## API and reporting

Extend the run-detail rewrite response with latest-cycle metrics:

```json
{
  "attempt_count": 3,
  "repair_count": 2,
  "outcome": "failed",
  "issue_codes": ["native_equation_structure_invalid"],
  "evidence_available": true
}
```

Add an authenticated detail endpoint or internal experiment report for attempt
evidence. Public/viewer responses should expose safe codes and counts by
default, not verbose evidence that may contain canonical assessment text.

Provide aggregate queries/report output for:

- successful sessions grouped by `repair_count`;
- failed sessions grouped by `repair_count`;
- success rate after zero, one, and two repairs;
- issue-code frequency by initial attempt, repair attempt, and terminal outcome;
- repair transition pairs, such as an equation-count error becoming a
  structure error.

## Test plan

### Provider tests

- Initial and repair calls use exactly the same container ID.
- Canonical JSON is uploaded once and Python source is not resent on repair.
- Repair instructions include only structured targeted evidence.
- Builder and DOCX named-file requirements are enforced.
- The container is deleted once after success, exhausted repairs, provider
  failure, verifier exception, and persistence failure.
- Expired-container failure produces `docx_container_expired`.

### Pipeline and persistence tests

- Initial success persists `attempt_count=1`, `repair_count=0`, successful
  outcome, and valid evidence.
- Initial non-repairable failure persists `attempt_count=1`, `repair_count=0`,
  failed outcome, and security evidence without an LLM repair call.
- One-repair success persists two attempts, `repair_count=1`, both reports, both
  artifact hashes, and successful outcome.
- Two-repair failure persists three attempts, `repair_count=2`, every report,
  and the final deduplicated issue codes.
- Provider failure during a repair still counts that repair call and persists a
  failed attempt.
- Container cleanup failure does not erase a verified successful outcome.
- A crash/retry cannot duplicate a cycle, attempt, or model usage.
- The original assessment remains canonical after terminal DOCX failure.

### Verifier tests

- Equation errors identify the correct stable label despite a missing or
  reordered preceding equation.
- Duplicate labels are rejected or resolved through the composite identity.
- Expected and actual structures are serialized without embedding unrestricted
  document text.
- Full verification detects collateral changes outside the requested target.

### API and reporting tests

- Successful and failed runs return accurate repair counts.
- Multiple rewrite cycles report the latest cycle separately from cumulative
  totals.
- Evidence detail is access-controlled and sanitized.
- Historical runs without session records return `null`/legacy status rather
  than fabricated zero counts.

Run the focused DOCX, worker, API, migration, and usage-tracking suites, then the
complete backend test suite. Run frontend tests if repair metrics are displayed
in the viewer or progress UI.

## Implementation sequence

1. Add failing model and migration tests, then introduce the two Luna persistence
   tables and relationships.
2. Add structured target/evidence fields to verification issues and convert
   equation findings from positional indexes to stable labels.
3. Refactor the provider into a reusable cycle-scoped container API with named
   files and idempotent cleanup.
4. Refactor the Luna generator to persist session/attempt boundaries, repair
   counts, hashes, feedback, and terminal outcomes.
5. Stop immediately on non-repairable findings and add expired-container
   handling.
6. Extend run-detail/reporting APIs with repair counts and protected evidence.
7. Update prompts and documentation, then run focused and full verification.

## Acceptance criteria

- One successful or failed Luna cycle uses one container across all attempts.
- Repair calls do not resend Python source or canonical JSON while the container
  is active.
- Every attempted repair is counted for both successful and failed outcomes.
- Every attempt has durable sanitized verifier evidence and artifact hashes.
- Repair findings refer to stable equation labels rather than only positional
  indexes.
- Non-repairable security findings never trigger another LLM call.
- The final DOCX passes complete verification; otherwise the original assessment
  remains available and the cycle is recorded as failed.
- Container deletion occurs after the cycle, including all exceptional paths.
