# Stable OpenAI Actual Prompt Design

## Objective

Make OpenAI Actual Prompts reproducible by rendering one canonical template instead of asking the model provider to regenerate the complete prompt for every run. Anthropic prompt generation remains unchanged.

## Scope

This change applies only to conditions whose prompt structure is `openai`. It preserves the existing prompt persistence, hashing, validation, assessment-generation, and run-tracking flow after the Actual Prompt has been constructed.

The canonical template is `docs/actual_prompt_template.md`. Its stable instructional wording must be used unchanged except for deterministic placeholder substitution and the approved conditional Additional Instruction row.

## Architecture

Add a deterministic OpenAI template renderer to the Actual Prompt service. The worker branches by prompt structure:

- For OpenAI, it builds the existing structured experiment input for traceability, renders the canonical template locally, and does not make an `actual_prompt` provider call.
- For Anthropic, it retains the existing provider-based compiler call and XML validation path.

Both branches persist the resulting Actual Prompt in the existing `Prompt` record and pass it through the existing assessment-generation call. Existing reproducibility hashes continue to include the rendered prompt and the inputs that produced it.

## Dynamic Values

The renderer replaces all named placeholders consistently wherever they occur, including repeated values in the Goal, Prompt Parameters, Concept Mapping, Prompt Design Factors, Output Format, metadata example, and Stop Rules.

The value mapping is:

- `learning_objective`: the experiment learning objectives.
- `course`: the experiment course.
- `topic`: the experiment topic.
- `question_type`: the experiment assessment type.
- `difficulty`: the experiment difficulty.
- `cognitive_demand`: the existing user-facing cognitive-demand label.
- `number_of_questions`: the requested question count.
- `estimated_time`: the experiment's estimated time in minutes, rendered with an explicit `minutes` unit.
- `mse202_concepts`: the topic when the course is MSE202; otherwise `Not Provided`.
- `mse302_concepts`: the topic when the course is MSE302; otherwise `Not Provided`.
- `concept_bridge`: the supplied Concept Bridge factor content when enabled; otherwise `Not Provided`.
- `materials_science_context`: an instruction telling the assessment model to derive an appropriate context from the supplied course, topic, and learning objective rather than inventing a new application input.
- `prompt_design_factors`: the names and complete supplied content of enabled factors. Disabled factors are omitted. If none are enabled, use `None Selected`.

Enabled factors retain their established ordering: Concept Bridge, Few-shot Examples, Reference Content, then Reasoning Guidance. Factor content is inserted verbatim after normal input trimming so examples and reference text remain usable.

When Additional Instruction is nonblank, add an `Additional Instruction` label and its exact trimmed content to the dynamic Prompt Parameters section. When blank, omit both the label and value without leaving excess placeholder text.

Course matching for the MSE concept fields is case-insensitive after trimming. A course other than MSE202 or MSE302 sets both course-specific concept fields to `Not Provided` rather than guessing.

## Template Safety

Literal braces belonging to the JSON example are not placeholders. The renderer recognizes only the approved named placeholders and preserves all other braces exactly.

Rendering fails before persistence if:

- the canonical template cannot be loaded;
- a required named placeholder has no mapped value;
- any approved named placeholder remains unresolved after rendering; or
- the rendered prompt fails the OpenAI Actual Prompt validator.

The template path is resolved from the application source tree, not the process working directory, so workers render the same file regardless of launch location.

## Validation

OpenAI validation is updated to match the canonical template's stable section structure rather than requiring the previous seven generated Markdown headings. It must still reject empty prompts, leading or trailing whitespace, code fences, unresolved approved placeholders, missing top-level `questions` contract text, duplicated stable sections, or sections in the wrong order.

Anthropic validation remains unchanged.

## Worker and Tracking Behavior

An OpenAI run records no model-call usage row for the `actual_prompt` stage because no provider call occurs. Its Prompt record uses deterministic local provenance for the structure model fields rather than fabricating a provider request identifier. The assessment-stage call, response schema, generation context, document sources, and downstream status transitions remain unchanged.

The Actual Prompt generator and structure/template versions are incremented so new deterministic prompts are distinguishable from prompts created by the earlier provider-generated flow.

## Testing

Tests must cover:

- byte-for-byte identical OpenAI rendering for identical inputs;
- changes only in the expected substituted values when inputs change;
- MSE202 and MSE302 topic-to-concept mapping, including case-insensitive course matching;
- `Not Provided` behavior for the opposite or unknown course concept field;
- derived materials-context instruction;
- enabled factor names and full content in stable order;
- omission of disabled factor content and `None Selected` when all factors are disabled;
- Concept Bridge content when enabled and `Not Provided` when disabled;
- conditional Additional Instruction inclusion;
- preservation of literal JSON braces and replacement of repeated placeholders;
- failure on unresolved approved placeholders or malformed template structure;
- no OpenAI `actual_prompt` provider call or usage record;
- unchanged Anthropic provider-generation behavior;
- persistence and reproducibility hashes using the rendered OpenAI prompt; and
- successful assessment generation with the rendered prompt.

## Non-goals

This work does not redesign the Anthropic Actual Prompt, add new experiment inputs, change the assessment response schema, alter source-document handling, or refactor unrelated prompt and worker code.
