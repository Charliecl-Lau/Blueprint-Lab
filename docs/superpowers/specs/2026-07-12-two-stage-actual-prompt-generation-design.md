# Two-Stage Actual Prompt Generation Design

## Purpose

Blueprint Lab currently combines its assessment-generation instructions and experiment inputs into a deterministic prompt and sends that prompt directly to the assessment model. This does not match the intended research workflow. Each run must instead use an LLM to generate a provider-structured prompt before using that generated prompt to produce the assessment.

This design introduces a two-call pipeline while preserving immutable runs, exact evidence, ordered source bindings, and reproducibility.

## Terminology

- **Structure System Prompt:** A pre-created, versioned system instruction that teaches the first LLM call how to construct either an OpenAI-structured or Anthropic-structured prompt.
- **Assessment Details:** The course, topic, learning objectives, assessment type, difficulty, and number of questions requested by the experiment.
- **Prompt Design Factors:** The enabled experimental factors and their inputs: concept bridge, few-shot examples, reference content, and reasoning guidance.
- **Actual Prompt:** The raw output of the first LLM call. It combines the Assessment Details and enabled Prompt Design Factors in the selected OpenAI or Anthropic prompt structure.
- **Generation:** The second LLM call, in which the Actual Prompt is the controlling system instruction and selected source content is supplied separately as context.
- **Generated Assessment:** The raw and parsed output of the Generation call.

These terms replace ambiguous uses of `system_prompt`, `final_prompt`, and generated prompt where practical. Compatibility mappings may remain at external or migration boundaries, but internal names must make the two stages explicit.

## Architecture

Each run performs two sequential LLM calls using the same selected model and model settings:

```text
Structure System Prompt
        +
Assessment Details
        +
Prompt Design Factors
        |
        v
First LLM call
        |
        v
Actual Prompt
        +
Selected Reference Context
        |
        v
Second LLM call
        |
        v
Generated Assessment
```

The OpenAI and Anthropic structures use separate Structure System Prompts. This keeps each provider structure independently testable and versionable and prevents rules for one structure from leaking into the other.

## First Call: Actual Prompt Generation

The first call uses the selected Structure System Prompt as its system message. Its user message contains only the Assessment Details and Prompt Design Factors for the condition.

Uploaded source-document content is not included in this call. A reference-content factor may tell the prompt writer how reference material should be used during Generation, but the source material itself remains isolated to the second call.

The first call must return only the Actual Prompt. It must not add commentary, planning notes, explanations, or Markdown code fences around the prompt. The application stores the raw response without rewriting it.

The selected structure determines the minimum validation rules:

- OpenAI Actual Prompts must contain the configured Markdown sections defined by the OpenAI Structure System Prompt.
- Anthropic Actual Prompts must contain the configured XML sections defined by the Anthropic Structure System Prompt, with balanced opening and closing tags.
- All Actual Prompts must be non-empty and free of surrounding commentary or code fences.

The application must reject a structurally invalid Actual Prompt rather than silently repair it. Silent repair would make the recorded model response differ from the instruction executed in the experiment.

## Second Call: Generation

The second call uses the raw Actual Prompt as its controlling system instruction. Blueprint Lab must not add another assessment system prompt, wrapper instruction, or competing schema instruction.

Selected source documents are assembled in their recorded binding order and supplied separately in the user/context message. If the run has no selected source documents, the user message contains only a neutral trigger requesting execution of the controlling instruction.

The Generated Assessment continues through the existing raw-response persistence, JSON parsing, assessment-schema validation, and DOCX export stages.

## Components

The pipeline is divided into units with narrow responsibilities:

- `StructurePromptBuilder` selects the versioned OpenAI or Anthropic Structure System Prompt and serializes the Assessment Details and Prompt Design Factors.
- `ActualPromptGenerator` performs the first LLM call and returns the raw Actual Prompt.
- `ActualPromptValidator` checks the output rules and provider-specific structure without modifying the response.
- `GenerationContextBuilder` assembles source content in immutable binding order.
- `AssessmentGenerator` performs the second call with the Actual Prompt as the system instruction and the assembled context as the user message.
- The existing assessment parser and DOCX exporter validate the Generated Assessment and create the artifact.

These boundaries allow provider structures, validation, context assembly, and assessment parsing to be tested independently.

## Persistence and Reproducibility

Each run must retain enough exact evidence to reconstruct both calls:

- Structure System Prompt and its version.
- Exact first-call user input.
- Raw Actual Prompt and its hash.
- Actual-prompt generator version.
- Selected prompt structure.
- Model settings used by both calls.
- Provider metadata for both calls when available, including request identifiers, model names and versions, finish reasons, and durations.
- Ordered source bindings and source hashes.
- Exact second-call context or an equivalent reproducible representation tied to immutable source snapshots.
- Raw Generated Assessment and its hash.
- Parsed assessment, schema version, and generated artifact.

The prompt hash or replacement call-envelope hashes must cover the exact instructions and inputs used at each stage. Hash serialization remains canonical and deterministic.

Existing `Prompt.system_prompt` and `Prompt.final_prompt` fields must either be migrated to explicit names such as `structure_system_prompt` and `actual_prompt`, or be documented as compatibility mappings at a narrow boundary. New internal code must use the explicit terminology.

Retrying a completed or failed run creates a new immutable run number. A retry repeats both LLM calls and therefore produces and records a new Actual Prompt; it never overwrites evidence from the earlier run.

## Status and Error Handling

Run progress must distinguish actual-prompt generation from assessment generation. Exact stage names may follow existing status constraints, but events and stored errors must identify the failing call unambiguously.

Errors use stage-specific categories:

- `actual_prompt_provider_error` when the first provider call fails.
- `actual_prompt_validation_error` when the first response is empty or violates the selected structure.
- `generation_provider_error` when the second provider call fails.
- `assessment_parse_error` when the Generated Assessment is not valid assessment JSON.
- `artifact_generation_error` when DOCX creation fails.

The raw first response is preserved before Actual Prompt validation. The raw second response is preserved before assessment parsing. A failure in either validation stage must therefore retain the evidence that caused it.

Provider retry behavior may retry transient calls within the same task according to the existing policy, but user-visible retry semantics remain immutable: explicitly retrying a run creates a new run and restarts the complete two-call pipeline.

## Testing

Automated coverage must verify:

- Selection and versioning of separate OpenAI and Anthropic Structure System Prompts.
- Exact serialization of Assessment Details and Prompt Design Factors for the first call.
- Exclusion of uploaded source content from the first call.
- Use of the same selected model and model settings for both calls.
- Preservation of the raw Actual Prompt without rewriting.
- Rejection of empty, fenced, annotated, or structurally invalid Actual Prompts.
- Required OpenAI Markdown structure and Anthropic XML structure.
- Use of the Actual Prompt as the second call's controlling system instruction.
- Inclusion of ordered source context only in the second call.
- Neutral second-call user content when no sources are selected.
- Persistence and hashing of both calls and their provider metadata.
- Stage-specific error classification and preservation of malformed responses.
- Immutable retry behavior across the complete two-call pipeline.
- End-to-end assessment parsing and DOCX export after a successful second call.

Tests built around the former deterministic, single-call prompt path must be replaced or updated so they do not preserve the incorrect architecture.

## Scope

This change covers Actual Prompt generation, Generation execution, evidence persistence, validation, statuses, and related tests. It does not introduce evaluation rubrics, reviewer workflows, automatic prompt repair, model selection per stage, or different model settings between calls.
