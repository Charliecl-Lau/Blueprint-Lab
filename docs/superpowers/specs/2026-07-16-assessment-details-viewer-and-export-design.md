# Assessment Details, Viewer, and Export Design

## Goal

Extend assessment setup with cognitive demand and optional additional instructions, make the viewer the sole token-usage display, improve condition and equation presentation in the viewer, and remove assessment-quality checks from generation and Word exports.

## Assessment Details

`Experiment` gains two persisted fields:

- `cognitive_demand` is required and defaults to `remember_understand`.
- `additional_instruction` is optional, trimmed, and stored as `NULL` when blank.

The supported cognitive-demand values and labels are:

| API value | User-facing label |
| --- | --- |
| `remember_understand` | Remember/Understand |
| `apply_analyze` | Apply/Analyze |
| `evaluate_create` | Evaluate/Create |

The Assessment Details step contains a required dropdown with Remember/Understand selected by default and an optional multiline Additional instruction text field. The Review step shows both values, using `None` when no additional instruction is supplied.

The experiment create API validates, persists, and returns both fields. The experiment detail response exposes them to the frontend. A database migration adds both columns, backfills existing experiments with `remember_understand`, and leaves their additional instruction empty.

## Prompt Data Flow

The worker passes the persisted values to `build_structure_input`. Cognitive demand is always included in the Assessment Details section using its user-facing label. Additional instruction is included only when nonblank. Both OpenAI and Anthropic structure-system prompts explicitly preserve cognitive demand and additional instruction among the supplied assessment requirements.

Assessment-quality checks are removed from the generation contract. `quality_check` is removed from the typed question response and provider schema, including the provider schema's required-field list. Both structure-system prompts stop listing or requesting quality-check output. Existing stored JSON containing `quality_check` remains readable because extra fields are tolerated and stored artifacts are not rewritten.

## Token Usage Presentation

Token accounting, persistence, API responses, and the shared `TokenUsage` component remain intact. The Progress page no longer renders token usage. The DOCX exporter no longer accepts or writes token-usage content. The viewer remains the only page that renders `TokenUsage`.

## Viewer Condition Presentation

The viewer header no longer displays prompt structure. The expandable Prompt and factor metadata section is removed entirely, including the actual-prompt text and factor-input JSON.

The Experiment Condition section shows the course, topic, cognitive demand, estimated completion time, and optional additional instruction. Instead of displaying the compact `condition_label`, it renders each experimental factor on a separate line with readable spacing:

- `Concept Bridge = ON`
- `Few-shot Examples = OFF`
- `Reference Content = ON`
- `Reasoning Guidance = OFF`

## Viewer Equation Rendering

A focused frontend math module defines the structured math node types, parses the supported legacy Word-linear expression subset, and renders semantic MathML. A reusable `MathContent` component renders question bodies, answer choices, and solutions by replacing `[[EQ:label]]` placeholders inline.

The renderer supports:

- text, symbols, numbers, operators, sequences, and equations;
- fractions;
- subscripts and superscripts;
- combined subscripts and superscripts using `msubsup` when the saved tree nests both scripts on the same base;
- square and indexed radicals;
- products and differentials;
- matrices.

It consumes structured `math` nodes when present. For equations saved as legacy linear `expression` strings, it parses the same subset used by the Word exporter: `/` fractions, `_` subscripts, `^` superscripts, combined scripts, and `sqrt(...)` radicals. If parsing fails, it displays the original expression as readable math text. Unknown structured nodes fall back locally without preventing the rest of the assessment from rendering.

Equation entries referenced by placeholders render at the placeholder location. Unreferenced entries render once as standalone equations in their declared question or solution location. Options and solutions use the same behavior as question bodies.

## DOCX Output

The DOCX retains run provenance, assessment metadata, generated questions, solutions, native OMML equations, and suggested revision options. It removes:

- the End-to-end token usage heading and values;
- the Assessment Quality Check heading and entries.

The worker stops passing token usage to the exporter. Previously generated DOCX artifacts are unchanged.

## Validation and Compatibility

Unsupported or missing cognitive-demand values use the existing structured Assessment Details validation response. Additional instruction is limited to 20,000 characters and is normalized before persistence. The frontend default ensures ordinary submissions always send a valid cognitive demand.

Existing experiments load after migration with Remember/Understand. Existing generated assessments with `quality_check`, structured math, or legacy linear equation entries continue to display. No token-usage records are deleted.

## Testing

Backend tests cover:

- schema defaults, supported cognitive-demand values, trimming, and invalid input;
- model persistence and migration backfill;
- create/detail API round trips;
- prompt-input propagation and omission of blank additional instruction;
- removal of quality-check requirements from provider and structure prompts;
- DOCX absence of token-usage and Assessment Quality Check content while preserving OMML equations;
- worker integration with the revised exporter interface.

Frontend tests cover:

- default and selectable cognitive demand;
- optional additional instruction submission and review display;
- absence of token usage on Progress;
- viewer-only token usage;
- separate factor-state rows and removed prompt/factor metadata;
- MathML rendering for inline and standalone equations, fractions, scripts, combined scripts, and radicals;
- readable fallback behavior for unsupported legacy expressions.

The final verification runs the focused backend and frontend tests, the complete backend test suite, the complete frontend test suite, linting, and the production frontend build.
