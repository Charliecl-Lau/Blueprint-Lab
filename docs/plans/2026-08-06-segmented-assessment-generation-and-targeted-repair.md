# Segmented Assessment Generation and Targeted Repair Plan

## Goal

Reduce assessment-generation latency and repeated full-JSON repairs by having the LLM identify prose and mathematics as ordered typed segments in a single response, then having the backend deterministically construct equation labels, `[[EQ:label]]` references, and the canonical `equations[]` array.

When validation still fails, collect all defects in one pass and regenerate only the affected question rather than the complete assessment.

## Approved design decisions

1. Initial assessment generation remains one LLM request. This change does not split initial generation into separate text and equation model calls.
2. The LLM returns ordered `text` and `math` segments. It does not invent equation labels or manually synchronize references with `equations[]`.
3. The backend compiles segments into the existing canonical flat fields and `equations[]` representation.
4. A repair request targets one complete question unit: body, options, model answer, and equations. These fields remain a shared validation boundary even when the reported defect appears only in the question or solution.
5. Validation reports every detectable defect in the affected question in one response rather than stopping at the first cross-field error.
6. Existing saved assessments, evaluation APIs, document generation, and canonical storage remain compatible with the current `body`, `model_answer`, `[[EQ:label]]`, and `equations[]` contract.

## Current behavior and problem

The provider-facing schema currently asks the model to return all of the following together:

- prose in `body`, option bodies, and `model_answer`;
- unique equation labels;
- `[[EQ:label]]` references placed at exact positions in the prose;
- a matching `equations[]` entry for every reference;
- the correct `question` or `solution` location; and
- exactly one reference for every equation entry.

The model therefore performs content generation and referential bookkeeping simultaneously. A raw expression left in prose, a repeated label, an incorrect location, or an unreferenced equation rejects the entire provider response. The worker then sends the full assessment JSON back for repair and requires another complete assessment response, even if only one question is invalid.

The canonical schema already contains `TextSegment`, `MathSegment`, `ContentSegment`, and optional segment fields. However, `ProviderQuestionResponse` still exposes only flat strings and a provider-authored `equations[]` array. The update should make typed segments the provider contract while retaining the existing canonical contract downstream.

## Target data flow

```text
One assessment LLM request
        |
        v
Provider JSON with ordered text/math segments
        |
        v
Deterministic segment compiler
  - assigns stable unique labels
  - inserts [[EQ:label]] references
  - derives equation locations
  - builds equations[]
        |
        v
Aggregated question and assessment validation
        |
        +-- valid --> persist canonical assessment --> document generation
        |
        +-- invalid --> repair only affected question(s), one at a time
                           |
                           v
                     compile, merge, and validate full assessment
```

## Provider response contract

### Segment types

Use the existing discriminated segment structure as the basis of the provider schema:

```json
{
  "type": "text",
  "text": "Using the heat capacity "
}
```

```json
{
  "type": "math",
  "expression": "C_p = 25 J/(mol K)",
  "display": false
}
```

The implementation must choose one canonical math representation for provider output:

- Prefer a simple linear `expression` string initially because the current provider schema and DOCX path already accept Microsoft Word linear equation syntax.
- Do not require the LLM to emit the full recursive `MathNode` tree in the first iteration unless testing demonstrates that the model produces it reliably and with acceptable token cost.
- Preserve an explicit inline/display hint if document rendering needs to distinguish embedded expressions from standalone derivation lines.

### Provider question shape

Replace provider-authored flat mathematical content and `equations[]` with segment collections:

```json
{
  "type": "short_answer",
  "metadata": {},
  "body_segments": [
    {"type": "text", "text": "For a material with "},
    {"type": "math", "expression": "C_p = 25 J/(mol K)", "display": false},
    {"type": "text", "text": ", calculate the temperature change."}
  ],
  "options": [],
  "model_answer_segments": [
    {"type": "text", "text": "The governing relation is"},
    {"type": "math", "expression": "q = C_p Delta T", "display": true}
  ],
  "quality_checks": [],
  "revision_options": []
}
```

Each MCQ option must use its own ordered `segments` collection. Short-answer and long-answer questions must use an empty options array. The provider must not return equation labels, `[[EQ:...]]` references, or an `equations[]` array.

### Prompt changes

Update the generation and repair prompts so that the model's responsibilities are explicit:

- Classify every output fragment as prose or math.
- Put complete equalities and derivation chains in one math segment.
- Do not put raw mathematical syntax in text segments.
- Keep symbols and short expressions inline through segment ordering.
- Mark substantive equations and derivation steps as display math.
- Do not create equation identifiers or references.
- Return the complete requested provider object and no prose outside JSON.

Remove obsolete instructions that ask the provider to invent labels, maintain reference uniqueness, set equation location, or build `equations[]`.

## Deterministic segment compiler

Create a dedicated service, for example `backend/services/assessment_segment_compiler.py`, that accepts one provider question plus its ordinal and produces one canonical `QuestionResponse` payload.

### Compilation rules

For each content field in document order:

1. Validate that the segment collection is non-empty where the corresponding content is required.
2. Concatenate text segments exactly, preserving intentional whitespace and paragraph boundaries.
3. For every math segment, generate a unique label from stable structural information rather than model content, such as:
   - question ordinal;
   - location (`question` or `solution`);
   - field identity (`body`, option ordinal, or `model_answer`); and
   - math occurrence ordinal within that field.
4. Insert `[[EQ:<generated-label>]]` into the flat output string at the segment's exact position.
5. Append one canonical equation entry containing the generated label, expression or math value, and derived location.
6. Derive `location="question"` for body and option segments and `location="solution"` for model-answer segments. Never accept location from the provider.
7. Generate a distinct equation entry for every math occurrence, even when two occurrences contain the same expression.
8. Preserve the inline/display intent in canonical structured content or rendering metadata without changing the meaning of the stored equation-reference contract.

Example compiled result:

```json
{
  "body": "For a material with [[EQ:q1_question_body_m1]], calculate the temperature change.",
  "model_answer": "The governing relation is\n\n[[EQ:q1_solution_answer_m1]]",
  "equations": [
    {
      "label": "q1_question_body_m1",
      "expression": "C_p = 25 J/(mol K)",
      "location": "question"
    },
    {
      "label": "q1_solution_answer_m1",
      "expression": "q = C_p Delta T",
      "location": "solution"
    }
  ]
}
```

### Compiler invariants

The compiler must guarantee by construction:

- labels are ASCII-safe and unique within a question;
- every equation entry has exactly one reference;
- every reference resolves to an equation entry;
- an equation cannot be referenced from both question and solution content;
- location matches the source field;
- no provider-supplied labels can collide with generated labels; and
- compilation is deterministic for identical provider input and question ordinal.

Compiler errors must be structured and include the question ordinal, field path, segment ordinal, issue code, and a bounded excerpt. Do not silently discard malformed or empty math segments.

## Aggregated validation

### Objective

Report all independently detectable issues in one validation pass so that a repair call receives the complete defect set for its target question.

### Validation structure

Introduce a structured issue type such as:

```json
{
  "code": "raw_math_in_text_segment",
  "question_ordinal": 2,
  "field_path": "model_answer_segments.4.text",
  "segment_ordinal": 4,
  "excerpt": "C_p = 25 J/(mol K)",
  "message": "Mathematical syntax must be represented by a math segment.",
  "repair_scope": "question"
}
```

Validation should collect, at minimum:

- raw equation syntax in text segments;
- empty text or math segments where prohibited;
- malformed math expressions;
- adjacent segment combinations that produce invalid or unreadable output;
- missing required question or solution content;
- incorrect MCQ option structure or correct-answer count;
- metadata mismatches;
- compiler invariant failures;
- canonical reference failures after compilation; and
- assessment-level question-count or metadata errors.

Pydantic remains the authoritative final schema validator. Add a pre-validation/audit layer for cross-field rules that currently raise on the first failure, or refactor those rules to build an issue list before raising one aggregate validation exception.

### Error ownership and repair scope

Map issue paths to repair scopes:

- Body or option segment defects: affected question.
- Model-answer segment defects: affected question.
- Equation or cross-location defects after compilation: affected question.
- Question metadata defects: affected question.
- Assessment metadata or question-count defects: assessment-level repair or a deterministic metadata correction when safe.
- Provider/network failures: retry policy, not content repair.

Although the UI or logs may describe an issue as belonging to the question or solution, the model repair unit remains the complete affected question because its body, options, model answer, and compiled equations share invariants.

## Question-scoped repair

### Repair request

When one or more issues belong to a question, send the model only:

- immutable assessment context needed to preserve intent;
- the affected question's provider-form segments and metadata;
- the complete aggregated issue list for that question;
- the expected provider question schema; and
- an instruction to return exactly one complete corrected provider question.

Do not send unrelated questions or request a full assessment response.

If multiple questions fail, repair them sequentially in ordinal order in the first implementation. This keeps token accounting, attempt limits, and merge behavior simple. Parallel repair can be considered later after measuring provider rate limits and merge safety.

### Merge procedure

For each corrected question:

1. Validate the provider question schema.
2. Compile its segments deterministically.
3. Run aggregated question validation.
4. Replace only the matching question ordinal in an in-memory candidate assessment.
5. Validate the complete merged assessment to catch assessment-level invariants.
6. Continue with the next invalid question if necessary.
7. Persist only after the complete merged assessment is valid or an existing explicitly approved warning/recovery path is selected.

Never merge by model-provided IDs alone. The server supplies and enforces the target ordinal, and immutable question identity must be preserved where applicable.

### Repair attempt limits

- Apply the existing maximum of three repair attempts per affected question, not three complete-assessment regenerations.
- A repair response must receive all current issues for that question on every attempt.
- Recompile and re-audit after each attempt because correcting one segment can expose a new interaction.
- Do not retry deterministic schema errors with the same payload.
- Keep transient provider retries separate from content-repair attempt counts.

## Persistence and compatibility

The first release should preserve the current canonical database and downstream interfaces:

- Persist compiled `body`, option bodies, `model_answer`, and `equations[]` exactly as downstream services expect.
- Optionally retain provider segment payloads in trace/debug storage if privacy and retention policy allow; canonical functionality must not depend on retaining them.
- Continue accepting legacy saved assessments that contain flat fields and equation references.
- Do not require migration of historical assessments.
- Keep evaluation, revision, export, and DOCX generation consumers operating on the canonical compiled form.

If segment fields are persisted canonically, establish a single source of truth. Prefer segments as the authoring representation and compiled flat fields as a deterministic materialization; add hash or consistency checks to prevent the two representations from drifting.

## Worker integration

Refactor the assessment portion of `backend/workers/assessment_worker.py` into explicit phases:

1. Generate provider assessment segments.
2. Validate the provider envelope.
3. Compile all provider questions into a canonical candidate.
4. Audit and group all issues by question ordinal.
5. Repair invalid questions within per-question limits.
6. Merge and validate the complete assessment.
7. Persist the canonical assessment and question records.
8. Continue to document generation.

Keep provider calls, usage recording, and progress publication outside pure compiler and validator services so those services remain deterministic and easily testable.

Add truthful progress messages such as:

- `Generating assessment content`
- `Structuring assessment equations`
- `Validating assessment`
- `Repairing question 2 of 5`

Do not expose a fabricated completion percentage.

## Observability and diagnostics

Persist every content-repair attempt rather than overwriting its evidence. At minimum record:

- run ID;
- question ordinal;
- repair attempt number;
- issue codes and field paths;
- provider call ID;
- input, output, cached, and reasoning tokens;
- elapsed provider time;
- compile and validation outcome; and
- whether the repaired question was merged.

Use structured issue codes for aggregation. Avoid relying on full free-form Pydantic messages as the primary metric.

Add metrics or queries for:

- percentage of initial generations valid without repair;
- frequency of each issue code;
- repairs per question and per run;
- question-scoped repair success rate;
- tokens and latency saved compared with full-assessment repair;
- raw-math-in-text false positives; and
- runs exhausting the per-question repair limit.

Correct the model-call timing fields or measurement path if `responded_at - created_at` can be negative. Use monotonic elapsed time for duration measurement and UTC timestamps only for event ordering.

## Testing plan

### Segment schema tests

- Accept ordered text and math segments for bodies, options, and solutions.
- Reject provider-supplied equation labels and canonical references.
- Reject malformed discriminators, missing content, and empty math expressions.
- Verify the OpenAI strict schema lists every object property in `required` and represents optional values through nullable types.
- Verify the Gemini schema adapter removes only unsupported JSON Schema features.

### Compiler unit tests

- Compile inline and display math while preserving exact order.
- Derive question and solution locations correctly.
- Generate unique labels across body, every option, and model answer.
- Generate separate labels for repeated expressions.
- Produce identical output for identical input.
- Preserve paragraph boundaries and intentional whitespace.
- Reject malformed segments with structured field paths.
- Validate the compiled result with `AssessmentGenerationResponse`.

### Aggregated validation tests

- Return multiple raw-math findings from one question in one audit.
- Return issues from body, options, and model answer together.
- Group issues by question ordinal.
- Distinguish question-scoped and assessment-scoped defects.
- Bound excerpts so logs and repair payloads do not contain excessive content.

### Worker and repair tests

- A valid initial segmented response makes exactly one assessment model call.
- One invalid question causes a repair request containing only that question.
- Unaffected questions remain byte-for-byte or canonically identical after merge.
- A solution-only issue still repairs and validates the complete question unit.
- Multiple issues in one question are supplied in one repair request.
- Two invalid questions are repaired independently in ordinal order.
- Per-question repair exhaustion follows the existing safe recovery/warning policy.
- Transient provider retries do not consume content-repair attempts.
- Token usage and attempt records are persisted for every call.
- Reference PDF attachments are included only when the affected question requires their grounding and retain the existing cleanup lifecycle.

### Regression tests

- Legacy flat assessments still load, evaluate, revise, and export.
- DOCX generation receives the same canonical equation-reference structure.
- Question traceability and ordinals remain stable after targeted merge.
- Existing recovery for explicit component symbols remains compatible or is retired only after equivalent segment validation is proven.
- Full assessment validation still runs after every targeted merge.

## Rollout strategy

1. Add the segment provider schema, compiler, aggregate issue model, and unit tests behind a configuration flag.
2. Run shadow compilation in non-production or test runs: generate using the existing contract while exercising compiler fixtures and comparing canonical invariants.
3. Enable segment-first generation for selected runs while retaining the existing full-assessment repair path as a temporary fallback.
4. Compare initial validity, repair rate, latency, token use, document verification, and semantic quality across both paths.
5. Enable question-scoped repair after segment compilation is stable.
6. Remove the legacy provider-authored label instructions and full-assessment repair fallback only after measured success criteria are met.

Fallback must be explicit and observable. Do not silently switch provider contracts within the same repair sequence, because that makes failures and token accounting difficult to interpret.

## Acceptance criteria

- Initial assessment generation uses one LLM request and returns typed text/math segments.
- The provider no longer creates equation labels, `[[EQ:label]]` references, locations, or `equations[]` entries.
- The backend deterministically compiles segments into the existing canonical representation.
- Compiled labels and references satisfy uniqueness, ownership, location, and exactly-once invariants by construction.
- Validation returns all detectable issues for an affected question in one structured result.
- A content defect repairs only the affected question unit, not the complete assessment.
- Unaffected questions are unchanged by targeted repair.
- The merged full assessment is validated before persistence and document generation.
- Repair evidence and token/latency measurements are retained per attempt.
- Existing saved assessments and downstream evaluation and DOCX workflows remain compatible.
- Tests demonstrate lower repair payload size and no loss of semantic content or equation rendering quality.

## Implementation order

1. Define provider segment schemas and structured validation issues.
2. Implement and test the pure deterministic segment compiler.
3. Implement aggregated segment and canonical question auditing.
4. Update generation prompts and provider response schema.
5. Integrate compilation into the worker behind a feature flag.
6. Implement question-scoped repair, merge, and per-question attempt limits.
7. Add repair-attempt persistence and reliable duration instrumentation.
8. Run regression, provider-contract, worker, evaluation, and DOCX tests.
9. Perform a measured staged rollout and remove the legacy full-assessment repair path after acceptance criteria are met.
