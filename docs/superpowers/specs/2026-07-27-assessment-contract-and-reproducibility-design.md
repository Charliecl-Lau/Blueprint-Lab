# Assessment Contract and Reproducibility Design

## Purpose

Blueprint Lab must preserve the exact inputs and effective settings used for
assessment generation while enforcing one assessment contract from experiment
submission through prompt rendering, provider validation, persistence, API
serialization, evaluation, and export.

This change corrects confirmed contract drift without replacing the existing
research data model. Experiments, conditions, runs, prompts, assessments, and
assessment questions remain separate relational records with independent
primary keys and traceability foreign keys. Evaluations and evaluation criteria
also remain separate.

## Sources of Truth

The following ownership rules are authoritative:

- Relational experiment, condition, run, prompt, assessment, and question
  records are authoritative for their database identifiers.
- A run's requested and effective execution configuration is captured in an
  immutable, versioned snapshot before provider execution.
- Provider-reported request and model-version values are observed execution
  results stored separately from requested and effective configuration.
- `prompts.actual_prompt` stores the generated Actual Prompt.
- Prompt execution fields store the exact system instruction and exact user
  message passed to the provider. The system instruction includes equation
  formatting requirements before it is persisted.
- `assessments.raw_response_text` is immutable provider evidence.
- `assessments.parsed_json` is the authoritative portable, validated, and
  application-enriched assessment snapshot.
- Relational IDs are authoritative if an embedded traceability snapshot ever
  disagrees. Normal application writes must keep both synchronized.
- `runs.generated_json` is not an application source of truth.

## Experiment Contract

`learning_objectives` becomes an array of nonblank strings throughout the
frontend, API, service, model, and prompt workflow. The frontend retains a
multiline text area and maps each nonblank trimmed line to one array item.
Existing database text is migrated conservatively into a single-item array so
historical punctuation is not interpreted as a delimiter.

The following columns are removed specifically from the `experiments` table:

- `description`
- `topic_area`
- `research_question`

Their SQLAlchemy mappings, API dependencies, fixtures, and tests are removed.
Other experiment columns, including `name` and `status`, remain.

Dropping the three columns discards values held only in those columns. A
downgrade may recreate their shape but cannot reconstruct discarded values.

## Run Execution Configuration

Run creation resolves effective configuration from explicit run values, API
values, environment defaults, and observable provider defaults. Resolution
occurs before dispatch so environment-backed values are never represented as
null.

The versioned execution snapshot distinguishes:

- requested provider;
- requested model;
- effective provider;
- effective model;
- temperature;
- `top_p`;
- maximum output tokens;
- seed when applicable; and
- provider-specific generation settings actually used.

Provider request ID, provider-reported model version, finish reason, duration,
and token usage remain observed results. They are not mislabeled as requested
configuration.

A retry creates a new run and copies the original run's effective execution
snapshot. It does not silently adopt later environment changes. Each run
therefore documents its own execution settings.

## Exact Prompt Reproduction

Prompt construction is completed before the prompt record is persisted. The
stored execution system instruction is byte-for-byte equal to the
`system_prompt` argument passed to the provider. The stored execution user
message is byte-for-byte equal to the provider's text payload.

The prompt record preserves:

- structure system prompt;
- structure input;
- generated Actual Prompt;
- exact generation system instruction, including equation requirements;
- exact generation user message or source-document payload;
- response-schema identifier or version;
- structure and Actual Prompt versions; and
- hashes computed from the exact persisted inputs.

Reference PDF descriptors are preserved as run attachments. The design does
not claim that remote provider file state is reproducible after provider-side
deletion; this limitation is reported explicitly.

Repair calls use separately composed repair instructions and recorded model-call
usage. The initial generation prompt record continues to represent the initial
assessment request, while repair-call evidence is retained through the model
call ledger and immutable raw assessment evidence.

## Concept Bridge Behavior

Concept Bridge is rendered as a conditional prompt block.

When the factor is off:

- bridge content is absent;
- bridge instructions are absent;
- bridge placeholders are absent; and
- no wording invites the model to invent a bridge.

When the factor is on:

- only the user-supplied bridge content is included;
- the exact enabled condition remains stored on the condition; and
- canonical assessment metadata may represent the supplied bridge content but
  may not invent a replacement.

Prompt snapshots cover both states.

## Canonical Assessment Contract

The provider schema, Pydantic validation model, repair validation, stored
assessment model, API types, frontend types, evaluation inputs, and exports use
the same field names and types.

Contract rules include:

- `learning_objectives` is always an array of nonblank strings.
- Estimated time uses one integer minutes field named
  `estimated_time_minutes`.
- `intended_assessment_setting` is removed from prompts, provider output,
  Pydantic models, stored metadata, APIs, frontend types, tests, and exports.
- Required question content, options, equations, quality checks, and revision
  options have identical required/optional behavior at every validation layer.
- Models reject unexpected fields rather than silently dropping requested or
  provider-returned data.
- Question metadata contains instructional content only; the application owns
  database traceability identifiers.

The provider-facing contract contains no database IDs. After validation and
database flush, the application enriches the stored assessment with a canonical
traceability structure.

Assessment-level traceability includes:

- experiment ID;
- condition ID;
- run ID;
- prompt record ID;
- prompt template identifier or version;
- assessment ID;
- assessment version; and
- assessment schema version.

Each stored question includes its `assessment_questions.id` and ordinal in its
traceability metadata. The application never asks the model to invent these
values.

The raw provider response is retained unchanged. Enrichment changes only the
validated `parsed_json` snapshot, after which its canonical hash is computed.

## Legacy `generated_json` Migration

The migration detects whether the deployed `runs` table still contains
`generated_json`.

For each useful legacy value:

1. If no assessment exists, create an assessment whose raw text is a canonical
   JSON rendering and whose parsed value preserves the legacy JSON.
2. If an assessment exists with equivalent data, retain it.
3. If an assessment exists with conflicting evidence, abort the migration and
   report the affected run IDs.
4. Verify counts, values, and hashes before removing the legacy column.

The migration never overwrites newer assessment evidence and never silently
chooses between conflicting records. Normal code, compatibility endpoints,
frontend viewers, and exports stop reading `runs.generated_json`.

Where legacy `parsed_json` contains `intended_assessment_setting`, migration or
versioned compatibility normalization removes it from the canonical stored
payload without changing `raw_response_text`. The assessment schema version
records the normalization.

## API, Frontend, Evaluation, and Export

Experiment request and response schemas expose `learning_objectives` as
`string[]`. The frontend converts multiline input into that representation and
renders arrays without delimiter inference.

Run and legacy generation endpoints return assessment output only from
`assessments.parsed_json`. The assessment viewer removes its generated-JSON
fallback.

Evaluation payloads use the canonical stored assessment and relational
traceability. They do not mutate the assessment snapshot.

DOCX and PDF exports display application-generated experiment, condition, run,
prompt, assessment, and question identifiers. They omit
`intended_assessment_setting` and display the canonical estimated-time and
learning-objective values.

## Migration Strategy

The forward migration:

1. converts experiment learning-objective text to JSON arrays;
2. removes the three approved experiment columns;
3. adds execution configuration and exact prompt-envelope fields;
4. reconciles any deployed `runs.generated_json` data safely;
5. normalizes legacy stored assessment metadata to the new schema version; and
6. adds constraints needed to prevent null effective settings and malformed
   snapshots.

The migration supports schema-state checks needed for deployments whose legacy
history disagrees with current SQLAlchemy models. It fails on ambiguous data
rather than continuing with data loss.

Downgrade is reversible where evidence remains available. It may recreate
removed experiment columns as nullable fields, but their discarded historical
values cannot be restored.

## Error Handling

- Invalid provider payloads produce explicit validation errors with field
  locations.
- Unexpected provider fields fail validation.
- Missing environment configuration fails before provider dispatch.
- Conflicting legacy generated output aborts migration with run IDs.
- Traceability enrichment runs in the same transaction as question
  persistence, preventing partially enriched canonical snapshots.
- Provider output remains available in raw form when parsing or enrichment
  fails.

## Test Strategy

Backend tests prove:

- runs without explicit settings persist all environment-backed effective
  values;
- retries preserve their own copied execution snapshot;
- requested, effective, and provider-observed model values remain distinct;
- valid representative provider responses pass the canonical contract;
- missing, mistyped, or extra fields fail without silent data loss;
- `intended_assessment_setting` is absent;
- real IDs appear only after persistence and are synchronized into
  `parsed_json`;
- raw responses remain unchanged during enrichment;
- Concept Bridge on/off prompt snapshots contain exactly the allowed content;
- persisted execution system and user inputs equal provider-call arguments;
- legacy generated JSON is preserved and conflicting data refuses migration;
- obsolete experiment columns are absent after migration; and
- API and exports use only `assessments.parsed_json`.

Frontend tests prove:

- multiline objectives become a nonblank string array;
- API payload and TypeScript types use the array contract;
- viewer code has no generated-JSON fallback; and
- metadata and export-facing views omit the removed assessment setting.

Verification runs targeted red/green tests during implementation, followed by
the complete backend suite, migration integration tests, frontend test suite,
and production frontend build.

## Existing Worktree Changes

The working tree already contains substantial uncommitted assessment-recovery
work that overlaps several affected files. Implementation must preserve that
work, avoid reverting unrelated edits, and integrate canonical-contract changes
with the warning/recovery states already being developed.

## Remaining Limitations

- Historical values from the three removed experiment columns cannot be
  reconstructed after upgrade unless separately backed up before migration.
- Raw historical provider responses may still contain removed or obsolete
  fields because immutable evidence is deliberately not rewritten.
- Exact text inputs and settings make generation auditable, but provider-side
  model behavior, service state, and deleted remote attachments cannot be
  recreated solely from the local database.
