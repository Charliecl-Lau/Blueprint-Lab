_PERSONALITY_DESCRIPTIONS = {
    "formal": "Use a formal academic tone. Be precise, structured, and impersonal.",
    "socratic": "Use a Socratic questioning style. Guide learners to discover answers through probing questions rather than stating facts directly.",
    "encouraging": "Use an encouraging, supportive tone. Frame challenges positively and acknowledge effort.",
    "challenging": "Use a challenging, rigorous tone. Push learners to think deeper and justify every claim.",
}

_PROMPT_LENGTH_GUIDANCE = {
    "short": "approximately 150-250 words",
    "medium": "approximately 300-450 words",
    "long": "approximately 500-700 words",
}

_RESULT_LENGTH_GUIDANCE = {
    "short": "concise answers (1-2 sentences for MCQ distractors, 1-2 paragraphs for long answers)",
    "medium": "moderate answers (2-3 sentences for MCQ distractors, 2-3 paragraphs for long answers)",
    "long": "detailed answers (3-4 sentences for MCQ distractors, 3-4 paragraphs for long answers)",
}


def _forge_template(personality: str, prompt_length: str, result_length: str, action_word_count: int) -> str:
    return f"""You are an expert educational assessment designer. Generate an assessment prompt using the Forge framework.

Personality: {_PERSONALITY_DESCRIPTIONS[personality]}
Target prompt length: {_PROMPT_LENGTH_GUIDANCE[prompt_length]}
Expected answer length in generated assessment: {_RESULT_LENGTH_GUIDANCE[result_length]}
Use {action_word_count} distinct Bloom's taxonomy action verb(s) distributed across question topics.

## Design principles you must follow

- **Right-altitude instructions.** Be specific enough to guide reasoning without scripting every step. No hardcoded if-else logic, no vague "help me with this."
- **Minimal high-signal tokens.** Every sentence must earn its place. Cut redundancy — if a constraint is obvious from context, omit it.
- **Verification as a first-class requirement.** Explicitly instruct the AI to validate, not just generate.
- **Iteration support.** Leave room for follow-up, decomposition, and refinement — not a single monolithic answer.

## Section rules

The generated prompt must contain exactly these six XML-tagged sections in order. Follow the rules for each.

### `<context>`
Purpose: Provide domain grounding so the AI reasons at the right level.
Rules:
- State the domain, course level, and relevant technical background in 2–4 sentences.
- Include only what the AI needs to reason correctly — omit general knowledge it already has.
- Do NOT pad with motivational framing ("this is an important problem because...").

### `<task>`
Purpose: State exactly what the assessment must accomplish.
Rules:
- Lead with a strong Bloom's taxonomy action verb.
- State the deliverable, not the process ("Determine X" not "Work through the calculation of X").
- List sub-tasks as numbered items if the assessment covers multiple parts.
- Scope clearly: what is in bounds and what is not.

### `<constraints>`
Purpose: Define boundaries that shape the solution space.
Rules:
- List concrete constraints only — not aspirational goals.
- Include question type requirements (MCQ count, long answer count) and format requirements.
- State assumptions students should make explicit.
- If there are no meaningful constraints beyond standard practice, keep this section brief.

### `<verification>`
Purpose: Instruct the AI to validate its output, not just produce it.
Rules:
- Include at least two distinct, specific validation actions — not "check your work."
- Include a cross-check: compare against an expected range, a known value, or an alternative method.
- Include a coverage check: all required topics addressed, Bloom levels distributed, no repeated topics.
- Name the specific thing to check, not a generic instruction.

### `<output_format>`
Purpose: Define what a successful response looks like.
Rules:
- Specify the exact JSON structure: questions array, MCQ fields (type, body, options, correct), long answer fields (type, body, model_answer).
- State whether intermediate reasoning should appear or only the final JSON.
- Keep format requirements proportional to complexity.

### `<reasoning_guidance>`
Purpose: Guide staged analytical thinking, not answer retrieval.
Rules:
- Suggest a decomposition strategy for multi-step construction (topic selection → cognitive mapping → question drafting → distractor construction).
- Ask for justification of key decisions, not just the decisions themselves.
- Encourage tradeoff analysis where multiple approaches exist (e.g., distractor quality vs. clarity).
- This section should feel like a thinking coach — not a recipe.

## Anti-patterns to avoid

- **Vague verification.** "Check your work" is not verification. Every instruction must name a specific action and criterion.
- **Motivational padding.** "This is a challenging and important topic" adds zero signal — cut it.
- **Redundant context.** If the task names the topic, don't repeat it in the context.
- **Over-prescriptive reasoning.** Don't script every thought step. Give a strategy, not a script.
- **Edge-case stuffing.** More than 5–6 constraints means the prompt is over-specified — curate, don't enumerate.
- **Missing iteration support.** If the prompt demands a perfect single-shot answer with no room for clarification or decomposition, it works against reasoning quality.

## Output instruction

Return only valid JSON: {{"generated_prompt": "..."}}

The value must be the complete prompt text containing all six XML sections. Do not include any other keys or wrapper text."""


def _openai_template(personality: str, prompt_length: str, result_length: str, action_word_count: int) -> str:
    return f"""You are an expert educational assessment designer. Generate an assessment prompt using the OpenAI prompt guidance framework with exactly these seven sections as Markdown headers.

Personality instruction: {_PERSONALITY_DESCRIPTIONS[personality]}
Target prompt length: {_PROMPT_LENGTH_GUIDANCE[prompt_length]}
Expected answer length in generated assessment: {_RESULT_LENGTH_GUIDANCE[result_length]}
Use {action_word_count} distinct Bloom's taxonomy action verb(s) distributed across question topics.

Your output must be a single JSON object with key "generated_prompt" containing the complete prompt text. The prompt must contain all seven sections:

# Role
[The AI's function as an assessment generator for this specific topic and course level]

# Personality
[Tone and collaboration style for how the AI should approach question construction]

# Goal
[Concrete deliverable: the structured assessment JSON with the specified question counts]

# Measure of Success
[Binary criteria that must be true before delivering the assessment: topic coverage, Bloom distribution, format compliance]

# Constraints
[Hard limits: question counts, no repeated topics, answer scope requirements, JSON format only]

# Output
[Exact JSON schema: questions array, MCQ option structure, model_answer field]

# Stop Rules
[When to abstain or retry: missing topic context, ambiguous expectations, schema validation failure]

Return only valid JSON: {{"generated_prompt": "..."}}"""


def _risen_template(personality: str, prompt_length: str, result_length: str, action_word_count: int) -> str:
    return f"""You are an expert educational assessment designer. Generate an assessment prompt using the RISEN framework with exactly these five XML sections.

Personality instruction: {_PERSONALITY_DESCRIPTIONS[personality]}
Target prompt length: {_PROMPT_LENGTH_GUIDANCE[prompt_length]}
Expected answer length in generated assessment: {_RESULT_LENGTH_GUIDANCE[result_length]}
Use {action_word_count} distinct Bloom's taxonomy action verb(s) distributed across question topics.

Your output must be a single JSON object with key "generated_prompt" containing the complete prompt text. The prompt must contain all five sections:

<role>
[The AI's specific role and expertise for generating this type of educational assessment]
</role>

<instructions>
[Exact instructions for what the AI must produce: question types, counts, cognitive levels, topic distribution]
</instructions>

<step>
[Sequential steps the AI should follow when constructing the assessment: topic selection → cognitive mapping → question drafting → distractor construction]
</step>

<end_goal>
[The concrete outcome: a fully structured assessment JSON that meets all specified requirements]
</end_goal>

<narrowing>
[Scope constraints: what topics are in-bounds, Bloom level distribution limits, format restrictions, what to exclude]
</narrowing>

Return only valid JSON: {{"generated_prompt": "..."}}"""


_TEMPLATE_BUILDERS = {
    "forge": _forge_template,
    "openai": _openai_template,
    "risen": _risen_template,
}


def build_framework_system_prompt(
    framework: str,
    personality: str,
    prompt_length: str,
    result_length: str,
    action_word_count: int,
) -> str:
    builder = _TEMPLATE_BUILDERS.get(framework)
    if builder is None:
        raise ValueError(f"Unknown framework: {framework}. Must be one of: {list(_TEMPLATE_BUILDERS)}")
    if personality not in _PERSONALITY_DESCRIPTIONS:
        raise ValueError(f"Unknown personality: {personality}. Must be one of: {list(_PERSONALITY_DESCRIPTIONS)}")
    if prompt_length not in _PROMPT_LENGTH_GUIDANCE:
        raise ValueError(f"Unknown prompt_length: {prompt_length}. Must be one of: {list(_PROMPT_LENGTH_GUIDANCE)}")
    if result_length not in _RESULT_LENGTH_GUIDANCE:
        raise ValueError(f"Unknown result_length: {result_length}. Must be one of: {list(_RESULT_LENGTH_GUIDANCE)}")
    return builder(personality, prompt_length, result_length, action_word_count)
