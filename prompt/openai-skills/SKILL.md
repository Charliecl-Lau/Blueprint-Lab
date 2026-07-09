---
name: openai-style-prompt
description: Generate structured prompts using the OpenAI prompt guidance framework. Use this skill whenever someone asks to generate a prompt using the OpenAI format, OpenAI-style framework, or mentions any of the seven sections: role, personality, goal, measure_of_success, constraints, output, stop_rules. Also trigger when someone says "generate an agent prompt", "write a system prompt using OpenAI structure", or "create a prompt with success criteria and stop rules". This skill produces prompts using the seven-section OpenAI prompt guidance format sourced from developers.openai.com/api/docs/guides/prompt-guidance.
---

# OpenAI-Style Prompt Generator

This skill generates structured prompts following the OpenAI prompt guidance framework published at developers.openai.com/api/docs/guides/prompt-guidance. It transforms a task description into a complete seven-section prompt optimized for goal-directed, agent-capable LLM behavior.

## What This Skill Does

The user provides a task, goal, or use case description. This skill produces a complete prompt structured with all seven OpenAI framework sections, each populated with content that is specific, actionable, and minimal — following OpenAI's core principle: "Keep each section short. Add detail only where it changes behavior."

## When to Use

- User says "generate a prompt using the OpenAI format/framework"
- User says "write a system prompt with role, personality, goal, stop rules"
- User asks to create an agent prompt, assistant prompt, or system prompt with success criteria
- User references the OpenAI prompt guidance page or the seven-section structure
- User wants a prompt for a task-focused AI assistant, agent, or product workflow

## Framework Reference

The seven sections are drawn directly from OpenAI's prompt guidance framework:

| Section | OpenAI Label | Purpose |
|---|---|---|
| `<role>` | Role | 1–2 sentences defining the model's function, context, and job |
| `<personality>` | Personality | Tone, demeanor, and collaboration style |
| `<goal>` | Goal | The user-visible outcome the model is working toward |
| `<measure_of_success>` | Success criteria | What must be true before the final answer is delivered |
| `<constraints>` | Constraints | Policy, safety, business, evidence, and side-effect limits |
| `<output>` | Output | Sections, length, and tone of the response |
| `<stop_rules>` | Stop rules | When to retry, fallback, abstain, ask, or stop |

## Workflow

1. Collect the task description and domain from the user
2. Read `references/framework-guide.md` for section-by-section rules and anti-patterns
3. Read `references/sample-output.md` to calibrate output quality
4. Generate the prompt following all seven sections
5. Deliver as a markdown file artifact

## Step 1 — Gather Input

Ask the user for:
- **Task or use case** (required) — what the AI assistant or agent will do
- **Audience or user type** (recommended) — who is interacting with the assistant
- **Domain and context** (recommended) — product area, technical domain, or workflow
- **Any hard constraints** (optional) — things the assistant must never do

If only a task is provided, infer reasonable defaults and state all assumptions explicitly at the top of the output.

## Step 2 — Read the Framework Guide

Before generating, read `references/framework-guide.md`. It contains:
- The exact rules and design principles for each of the seven sections
- Anti-patterns to avoid (verbosity, vague goals, missing stop rules)
- OpenAI's core design philosophy: outcome-first, minimal but complete

## Step 3 — Generate the Prompt

Produce a prompt with all seven sections populated. Rules:
- Every section must be present — no section may be omitted even if brief
- Sections are written as Markdown `#` headers, not XML tags (OpenAI convention)
- Each section should be the shortest version that fully defines the expected behavior
- `<measure_of_success>` and `<stop_rules>` are the most commonly under-specified sections — give them real content, not placeholders
- Do not add sections beyond the seven — no invented extensions

## Step 4 — Deliver

Output as a markdown file. Include a one-line header identifying the framework used and the task it was generated for.

## Quality Criteria

A well-generated prompt:
- Could be dropped into a system prompt and immediately produce correct behavior
- Has a `<goal>` that names a concrete user-visible outcome, not a process
- Has `<measure_of_success>` criteria that are binary (either true or false before responding)
- Has `<stop_rules>` that name specific trigger conditions — not generic "stop if confused"
- Has `<personality>` that shapes experience without overriding task behavior
- Has `<constraints>` that are concrete limits, not aspirational guidelines
- Has `<output>` that specifies structure and length, not just "be clear"
