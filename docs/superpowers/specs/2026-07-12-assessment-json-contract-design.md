# Assessment JSON Contract Design

## Problem

The structure-generation call can produce an Actual Prompt that requests valid JSON
without requiring the backend's `{"questions": [...]}` root shape. Such a prompt passes
structural validation, but the assessment-generation response later fails parsing.

## Design

Both provider-specific structure system prompts must require the later model's JSON
response to be an object with a top-level `questions` array. Actual Prompt validation
must reject generated prompts that do not mention that exact root field, preventing an
incompatible prompt from reaching the second model call.

The response parser remains strict. It will not silently wrap a single question because
that would conceal prompt-contract drift and could accept incomplete model output.

## Verification

Regression tests cover both structure instructions, rejection of prompts without the
contract, and acceptance of OpenAI and Anthropic prompts that include it. Existing worker
tests verify that pipeline behavior remains intact.
