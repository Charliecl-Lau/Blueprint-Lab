# Cross-Location Equation Label Repair Design

## Goal

Prevent generated assessments from failing when the same equation label is
referenced in both student-facing question content and the instructor solution.
Preserve the existing strict equation-location contract by requiring distinct
labels for question and solution occurrences of the same mathematical
expression.

## Production Evidence

Run 19 reached assessment generation after the OpenAI Actual Prompt template
was packaged successfully. Gemini returned an assessment, Pydantic rejected it,
and the worker made its existing single repair call. The repaired response still
failed with `question equation referenced from solution: g_mix_def`.

The persisted repaired response used six labels in both the question body and
`model_answer`: `g_mix_def`, `g_mix_res`, `h_mix_val`, `s_mix_def`, `temp`, and
`xa_val`. Each equation entry declared `location: "question"`. The current
validator stopped at the first mismatch, so the repair model did not receive a
complete description of the cross-location conflicts. The generation and repair
instructions require unique labels and a location but do not explicitly state
that one label cannot span question and solution content.

Local database run 50 provides a controlled comparison. It completed at 6:40 AM
EDT with the same Actual Prompt hash as deployed run 19, the same
`gemini-3.1-flash-lite` model, temperature `0.2`, top-p `0.95`, maximum output
of 32,768 tokens, no seed, and no source documents. Its first provider response
used disjoint question and solution labels and passed validation. Deployed run
19 reused six labels across the two locations, and its repair response retained
the conflicts. The defect is therefore exposed by nondeterministic provider
output under an ambiguous contract, not by a localhost/Railway configuration
difference. Local run 49 also recorded a separate equation-reference validation
failure shortly before run 50, confirming that the local environment could
produce invalid equation contracts as well.

## Equation Reference Contract

Each equation label belongs to exactly one content side:

- `location: "question"` labels may appear only in the question body or answer
  option bodies.
- `location: "solution"` labels may appear only in `model_answer`.
- When the same mathematical expression is needed in both places, the response
  must contain two equation entries with distinct labels and matching locations.
  Reusing the expression text is allowed; reusing the label is not.

For example, a Gibbs mixing definition used in both places should use labels
such as `g_mix_question` and `g_mix_solution`, with each reference pointing to
the entry for its own location.

## Prompt and Repair Guidance

The shared equation-generation instruction will state the cross-location rule
explicitly. Because the worker prepends this instruction to assessment calls and
repair calls, the rule will apply to both OpenAI-structure and
Anthropic-structure conditions.

The deterministic OpenAI Actual Prompt template will reinforce the same rule so
its constraints remain self-contained and consistent with the shared wrapper.
The repair instruction will tell the model to audit all equation labels across
the complete question, not merely the first label named in a validation error.
When a label spans both sides, repair must create distinct entries, rewrite the
references for their respective locations, and preserve the mathematical
expression and assessment meaning.

Prompt and generator version constants will be incremented so new runs using the
corrected contract are distinguishable from earlier generations.

## Validation Feedback

The `QuestionResponse` model validator will compute the set of labels referenced
from question content and the set referenced from solution content. It will
check their intersection before the existing per-location checks.

If the intersection is nonempty, validation will raise one focused error that
lists every shared label in stable sorted order. This gives the one-shot repair
call a complete conflict set. Existing validation remains responsible for
unknown labels, duplicate equation entries, unreferenced entries, individual
location mismatches, and mathematical expressions left outside equation
references.

The validator will not rewrite generated output. The accepted repaired response
remains the exact provider response stored for provenance.

## Worker Data Flow

The existing bounded workflow remains unchanged:

1. Generate an assessment using the strengthened equation contract.
2. Validate the complete response with `AssessmentGenerationResponse`.
3. If schema validation fails, make one repair call containing the rejected
   response and complete validation feedback.
4. Validate the repaired provider response once.
5. Persist parsed JSON and create the DOCX only when validation succeeds.
6. If the repair is still invalid, persist the assessment parse error without
   creating an artifact.

No additional provider calls, retry loop, or silent backend normalization will
be introduced.

## Testing

Tests will cover:

- shared generation and repair instructions explicitly requiring distinct
  question and solution labels;
- the OpenAI template containing the same cross-location rule;
- a run-19-shaped payload reporting all six shared labels in one validation
  error;
- continued rejection of a single non-shared label whose declared location is
  incorrect;
- acceptance of equivalent question and solution expressions when they use
  distinct labels and matching locations;
- worker repair of a cross-location response into a valid split-label response;
- preservation of the existing one-repair limit and model-call accounting; and
- the focused prompt, schema, worker, DOCX, and full backend test suites.

## Non-Goals

This change will not relax location validation, allow one label to span both
content sides, mutate provider responses in the backend, add database fields,
change API or frontend response shapes, alter DOCX equation rendering, retry old
failed runs automatically, or introduce more than one repair call.

## Success Criteria

- New generation and repair prompts unambiguously require location-specific
  labels.
- Cross-location validation reports every conflicting label at once.
- A repaired response with distinct labels passes validation and DOCX creation.
- An invalid repair still stops safely after one attempt.
- Existing unrelated local changes remain untouched.
- All targeted and full backend verification passes before deployment.
