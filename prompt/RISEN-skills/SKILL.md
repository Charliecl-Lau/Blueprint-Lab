---
name: risen-framework-prompt
description: Generate structured prompts using the RISEN framework (Role, Instruction, Structure, Examples, Nuance). Use this skill whenever someone asks to generate a prompt using RISEN, mentions any of the five RISEN components by name, or wants a prompt that controls AI tone, format, style, and examples together. Also trigger for "write a RISEN prompt", "generate a structured prompt with examples and nuance", or "create a prompt using the Role Instruction Structure Examples Nuance framework". This skill produces prompts following the RISEN methodology sourced from the RISEN framework article at medium.com.
---

# RISEN Framework Prompt Generator

This skill generates structured prompts following the RISEN framework: Role, Instruction, Structure, Examples, Nuance. It transforms a task or use case description into a complete five-section prompt designed to produce precise, consistent, and well-formatted AI outputs.

## What This Skill Does

The user provides a task, goal, or use case. This skill produces a complete RISEN prompt with all five sections populated — following the framework's core principle: a well-structured prompt is like a recipe. It doesn't just name the dish — it specifies ingredients, steps, and presentation.

## When to Use

- User says "generate a prompt using RISEN" or "write a RISEN prompt"
- User mentions Role, Instruction, Structure, Examples, and Nuance together
- User wants control over AI tone, format, output style, and few-shot examples in a single prompt
- User wants a prompt framework suited to creative, technical, and business tasks alike
- User asks for a structured prompt that includes examples to guide AI behavior

## Framework Overview

RISEN stands for five components that together define every aspect of a prompt:

| Letter | Section | Job |
|---|---|---|
| R | Role | Define the AI's persona, expertise, and perspective |
| I | Instruction | State exactly what the AI must do — specific and actionable |
| S | Structure | Specify the format and organization of the output |
| E | Examples | Provide input-output demonstrations (few-shot learning) |
| N | Nuance | Set tone, length, style, and boundary constraints |

## Workflow

1. Collect the task description and context from the user
2. Read `references/framework-guide.md` for section-by-section rules and anti-patterns
3. Read `references/sample-output.md` to calibrate output quality and tone
4. Generate the RISEN prompt with all five sections populated
5. Deliver as a markdown file artifact

## Step 1 — Gather Input

Ask the user for:
- **Task or use case** (required) — what the AI will be asked to do
- **Intended audience** (recommended) — who the AI is talking to
- **Domain or context** (recommended) — technical field, product area, or workflow
- **Tone or style preferences** (optional) — feeds into Nuance
- **Any existing examples** (optional) — input-output pairs the user wants to include

If only a task is provided, generate reasonable defaults and state all assumptions clearly at the top of the output.

## Step 2 — Read the Framework Guide

Before generating, read `references/framework-guide.md`. It contains:
- Rules and principles for each of the five sections
- What strong vs. weak versions of each section look like
- Anti-patterns to avoid (vague roles, missing examples, over-constraining nuance)
- The framework's distinguishing philosophy: show, don't just tell

## Step 3 — Generate the RISEN Prompt

Produce a complete prompt with all five sections. Rules:
- All five sections must be present — none may be omitted
- Sections use bold Markdown labels: **Role**, **Instruction**, **Structure**, **Examples**, **Nuance**
- Role must name a specific persona with relevant expertise — not a generic "helpful assistant"
- Instruction must use actionable verbs and be specific enough that two different people reading it would produce the same output
- Structure must name a concrete format — not just "organize clearly"
- Examples must include at least one input-output pair — do not leave this section as a placeholder
- Nuance must name at least two concrete constraints (tone + length, or tone + exclusion)

## Step 4 — Deliver

Output as a markdown file. Include a one-line header identifying the framework and the task it was generated for.

## Quality Criteria

A well-generated RISEN prompt:
- Has a Role that changes the depth and tone of the response — not decorative
- Has an Instruction specific enough to be tested: could you verify whether the AI followed it?
- Has a Structure that names the exact format (table, bullet list, numbered steps, code block)
- Has at least one real Example with a concrete input and expected output — not a template
- Has Nuance constraints that are specific and enforceable ("Under 150 words" not "be concise")
- Could be handed to any LLM and produce a consistent, predictable output
