# Bounded Assessment Repair Design

## Problem

Assessment generation can return JSON that passes the provider schema but fails
the application's stricter equation-reference validation. The worker currently
makes one repair call. If that response still contains plain mathematical text,
the run fails even when another focused repair could correct it.

Run 56 demonstrated this behavior: the initial response failed validation, the
repair response still included an inline `alpha = ...` expression, and the
worker recorded an `assessment_parse_error`.

## Decision

Keep equation-reference validation strict and allow at most two repair calls
after the initial assessment-generation call. Each repair call receives the
latest rejected response and its latest Pydantic validation error. A successful
repair immediately continues through persistence and document generation. If
both repairs fail validation, the existing parse-error behavior remains.

The existing `repair` usage stage will be reused for both calls. Its current
attempt calculation and token aggregation already distinguish and total
multiple calls without changing the API or database schema.

## Alternatives Considered

- Loosen equation validation. Rejected because inline mathematical text would
  bypass the editable OMML equation contract and could produce inconsistent
  DOCX output.
- Rewrite equations deterministically in the backend. Rejected because reliably
  extracting arbitrary mathematical expressions from prose and assigning their
  locations is ambiguous and risks changing assessment meaning.
- Retry the entire generation. Rejected because it discards otherwise useful
  content, costs more tokens, and is less targeted than repairing the rejected
  response.

## Worker Flow

1. Generate the assessment once and persist its raw response and usage.
2. Validate the latest raw response.
3. On validation failure, request a repair using that response and error.
4. Persist the repaired raw response, request metadata, hash, duration, and
   usage before validating it.
5. Repeat steps 2 through 4 for no more than two repair calls.
6. Continue the existing success path after the first valid response, or record
   the existing `assessment_parse_error` after the final invalid response.

Provider errors and unavailable reference-PDF errors retain their existing
classification and exit behavior on every repair call.

## Testing

Add a worker test in which the initial assessment and first repair fail the
equation-reference validator while the second repair succeeds. Verify three
model calls, two `repair` usage records, persistence of the final response, and
normal evaluation dispatch. Existing one-repair success and terminal validation
failure tests must continue to pass.

## Out of Scope

- Changing the equation-reference validator or provider schema.
- Adding user-configurable repair limits.
- Retrying provider failures differently.
- Reprocessing run 56 without a new reference-PDF upload.
