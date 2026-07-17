# Equation Generation Contract Design

## Goal

Ensure future assessment generations persist a complete, internally consistent
equation contract so both the assessment viewer and generated DOCX render saved
mathematics semantically. Existing assessments and artifacts remain immutable.

## Problem

OpenAI-structure conditions now use the deterministic local Actual Prompt
template. That template conflicts with the equation-placement instruction: it
requires `[[EQ:label]]` references but later prohibits all placeholder text. Its
JSON example also omits equation references from question and solution content.

The assessment response schema compounds the problem by defining `equations`
without requiring it. The Pydantic model defaults a missing array to an empty
list and does not validate relationships between equation entries and content.
An assessment can therefore be accepted as complete even when mathematical
expressions remain as plain text or equation labels are missing, duplicated,
unreferenced, or assigned to the wrong location.

## Scope

The change applies only to newly generated assessments. It does not update,
regenerate, or reinterpret existing database rows or DOCX artifacts.

The implementation will change:

- the deterministic OpenAI Actual Prompt template;
- prompt-contract validation tests;
- the provider JSON schema for assessment generation;
- Pydantic validation of generated question equation references; and
- worker tests proving invalid generation output is rejected before artifact
  creation.

The implementation will not change the MathML renderer, OMML serializer,
database schema, API response shape, or existing-run behavior.

## Prompt Contract

The local Actual Prompt must state that `[[EQ:label]]` is a required equation
reference, not prohibited placeholder text. The stop rule will prohibit only
unresolved template variables such as `{topic}` and explanatory placeholder
values such as `"..."` in the returned JSON.

The Output Format example will include:

- one equation referenced from `body` with `location: "question"`;
- one equation referenced from `model_answer` with `location: "solution"`;
- unique ASCII labels shared exactly by the content reference and equation
  entry; and
- Word-linear expressions using `/`, `_`, `^`, and `sqrt(...)` notation.

The existing generation-time equation instruction remains prepended to every
Actual Prompt. The local template will reinforce rather than contradict it.

## Provider Schema

Every generated question must include an `equations` array. The array may be
empty only when the question body, answer options, and model answer contain no
mathematical expression requiring semantic rendering.

Requiring the property prevents an omitted array from silently becoming an
empty default. Array content and cross-field relationships remain the
responsibility of Pydantic validation because JSON Schema cannot express label
uniqueness and reference integrity across these fields.

## Question Validation

A model-level validator on `QuestionResponse` will validate the complete
question after field parsing.

It will enforce these invariants:

1. Equation labels are unique within a question.
2. Every `[[EQ:label]]` reference resolves to exactly one equation entry.
3. Every equation entry is referenced at least once.
4. An equation with `location: "question"` is referenced only in `body` or an
   option body.
5. An equation with `location: "solution"` is referenced only in
   `model_answer`.
6. Obvious Word-linear or equation-like syntax is not left in plain content
   outside `[[EQ:label]]` references.

The plain-content check will be deliberately conservative. It will remove valid
equation references before scanning and reject strong equation signals:

- an equals sign between non-whitespace operands;
- Word-linear subscript or superscript operators between identifier/number
  tokens;
- `sqrt(`; and
- Markdown/LaTeX math delimiters already forbidden by the prompt.

It will not reject isolated variable names, ordinary prose punctuation,
hyphenated words, temperatures, units, percentages, or comparison prose. This
keeps false positives bounded while catching the demonstrated failure where
complete formulas containing `=` were left in the body and solution.

Validation errors will identify the question field and offending invariant so
generation failures remain diagnosable. The worker's existing assessment parse
error path will record the failure and will not create a DOCX artifact.

## Data Flow

For a future OpenAI-structure run:

1. The local renderer fills the canonical Actual Prompt template.
2. The worker prepends the shared equation-generation instruction.
3. The provider returns structured JSON under the strengthened provider schema.
4. `AssessmentGenerationResponse` validates each question and its equation
   references.
5. Only validated JSON is persisted as `parsed_json` and passed to both the DOCX
   exporter and assessment viewer.

The renderer paths remain deterministic consumers. Correctness is enforced at
the generation boundary before either consumer receives data.

## Testing

Tests will follow red-green development and cover:

- the local prompt explicitly permitting and demonstrating `[[EQ:label]]`;
- the provider schema requiring `equations`;
- acceptance of a valid body/solution equation payload;
- rejection of duplicate labels;
- rejection of missing-label references;
- rejection of unreferenced equations;
- rejection of question/solution location mismatches;
- rejection of the run-47 pattern where formulas containing `=` remain outside
  equation references; and
- worker behavior that records an assessment parse error and creates no
  artifact for an invalid response.

Focused prompt, schema, worker, OMML, and MathML tests will run before the full
backend and frontend verification suites. The frontend and DOCX renderer tests
must remain unchanged and green, demonstrating that the fix is confined to the
shared generation contract.

## Success Criteria

- New prompts contain no contradiction about equation references.
- Newly accepted questions have complete, resolvable, location-correct equation
  references.
- Formula-like plain text matching the conservative detector cannot be accepted
  as a complete generated assessment.
- Invalid generations stop before DOCX creation and expose the existing
  assessment-parse error state.
- Existing assessments and artifacts are unchanged.
- Backend tests, frontend tests, lint, and production build pass.
