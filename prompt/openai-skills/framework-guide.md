# OpenAI Prompt Framework — Section-by-Section Guide

Source: developers.openai.com/api/docs/guides/prompt-guidance

This file defines how each of the seven sections should be written, what each one is for, and what to avoid. Read this in full before generating any prompt.

---

## Core Design Philosophy

OpenAI's framework is built around three principles:

**1. Outcome-first.** Describe what a successful response looks like, not the steps to get there. The model should have room to choose an efficient path. Only specify the exact path when it materially matters.

**2. Minimal but complete.** Every section must be present. Every sentence in every section must earn its place. If a sentence does not change behavior, cut it.

**3. Sections have distinct jobs.** `<role>` is not `<goal>`. `<personality>` is not `<constraints>`. Bleeding content between sections creates ambiguity. Keep each section's content exclusive to its job.

---

## Section Rules

### `# Role`

**Job:** Define who the model is and what its function is in this context.

**Format:** 1–2 sentences maximum. Name the function, the context, and the scope.

**Rules:**
- State what the model *is*, not what it should *try to be*
- Include the operational context (product, platform, workflow)
- Do not include personality, goals, or constraints here — those have their own sections
- Avoid inflated titles ("world-class expert") — they add no behavioral signal

**Example:**
```
# Role
You are a workflow analysis assistant for Forge, an educational analytics platform. You help instructors evaluate student AI collaboration sessions and surface scoring insights from workflow data.
```

**Anti-patterns:**
- "You are a helpful and knowledgeable assistant who always tries to do your best" — vague, no context
- "You are an expert in everything" — no behavioral change
- Including tone or personality here — belongs in `# Personality`

---

### `# Personality`

**Job:** Shape how the model communicates — tone, demeanor, and collaboration style.

**Format:** 3–6 sentences. Describe the experience the user should have, and the working style the model should adopt.

**Rules:**
- Personality should shape the user experience; collaboration instructions should shape task behavior
- Neither replaces clear goals, success criteria, or stopping conditions
- Avoid personality instructions that contradict the task (e.g., "be warm and patient" for a triage-speed workflow)
- Include one collaboration instruction: how the model handles ambiguity and when it asks vs. proceeds

**Example:**
```
# Personality
You are capable, approachable, and direct. Assume the user is competent and acting in good faith. Prefer making progress over stopping for clarification when the request is already clear enough to attempt. Ask only when missing information would materially change the answer. Stay concise without becoming curt.
```

**Anti-patterns:**
- "Be friendly and helpful" — no behavioral specificity
- Personality that contradicts the task domain
- Using personality to smuggle in task rules — those belong in `# Constraints`

---

### `# Goal`

**Job:** Define the user-visible outcome the model is working toward.

**Format:** 1–3 sentences. State the concrete deliverable or end state.

**Rules:**
- Name the outcome, not the process
- The goal should be specific enough that success is recognizable
- Use precise action verbs: produce, identify, generate, resolve, classify
- Avoid: "help users", "assist with", "support" — these are process descriptions, not outcomes

**Example:**
```
# Goal
Produce a structured workflow evaluation report for the submitted student session, identifying scoring signals across PDS, VS, ES, and IIS dimensions and flagging any anomalies that require instructor review.
```

**Anti-patterns:**
- "Help the user with their question" — process, not outcome
- Goals that describe what the model should do internally rather than what the user receives
- Multiple goals in one section — if there are two goals, they are two tasks

---

### `# Measure of Success` (Success Criteria)

**Job:** Define what must be true before the model delivers the final answer.

**Format:** Bullet list of binary criteria. Each criterion must be independently verifiable as true or false before responding.

**Rules:**
- Every criterion must be binary — either satisfied or not
- Criteria should be checkable by the model before output, not evaluated by the user afterward
- Minimum 2 criteria, maximum 5 for most tasks
- Include at least one evidence or grounding criterion (the model has sufficient information to answer) and one completeness criterion (the answer addresses the full scope of the request)
- This section is the most commonly under-specified — do not leave it as one vague criterion

**Example:**
```
# Measure of Success
- All four scoring dimensions (PDS, VS, ES, IIS) have been evaluated with at least one signal identified per dimension
- Any dimension with insufficient data has been explicitly flagged rather than scored with a default
- The report structure matches the specified output format exactly
- No claim is made about student intent or ability — only observable workflow behavior is referenced
```

**Anti-patterns:**
- "The answer is correct and complete" — not binary, not checkable before output
- Single-criterion sections — almost always under-specified
- Criteria that describe output style rather than task completion

---

### `# Constraints`

**Job:** Define the hard limits on what the model can do, say, or assume.

**Format:** Bullet list. Each constraint is a specific, enforceable limit.

**Rules:**
- Constraints are limits, not guidelines — write them as hard rules
- Cover: scope limits (what is out of bounds), evidence rules (what the model can claim), safety limits, and side-effect limits (what it must not modify or trigger)
- Do not use aspirational language ("try to avoid", "prefer not to") — every constraint should be absolute
- Keep the list short — if a constraint appears obvious from the role and goal, omit it

**Example:**
```
# Constraints
- Evaluate only observable workflow signals — do not infer student intent, motivation, or ability
- Do not modify session data, scores, or database records — this is a read-only analysis tool
- Do not produce a score for a dimension if the session contains fewer than two interaction turns
- Do not reference student names or identifiers in the report output
```

**Anti-patterns:**
- "Try to be accurate" — not a constraint, it's an aspiration
- Constraints that contradict the goal
- Safety theater constraints that add length without changing behavior

---

### `# Output`

**Job:** Define the structure, length, and tone of the response.

**Format:** 2–4 sentences or a short bullet list. Specify sections, approximate length, and any formatting requirements.

**Rules:**
- Specify the response structure (sections, headers, tables, lists) not just the tone
- Name required sections if the output has a fixed shape
- Set a length expectation (concise, medium, detailed) — OpenAI guidance recommends starting with "low" verbosity for production and adjusting up
- If the output has a machine-readable component (JSON, table), specify the schema or column names

**Example:**
```
# Output
Produce a structured report with four sections: (1) Session Overview — 2–3 sentences summarizing the workflow, (2) Dimension Scores — one paragraph per dimension with signal evidence, (3) Anomaly Flags — bulleted list of issues requiring instructor review, (4) Recommended Actions — 1–3 specific next steps. Total length: medium. Use plain prose in all sections except Dimension Scores, which should use a table.
```

**Anti-patterns:**
- "Respond clearly and concisely" — no structural information
- Specifying tone here instead of in `# Personality`
- Output format that conflicts with the goal

---

### `# Stop Rules`

**Job:** Define when the model should not continue — when to retry, fallback, abstain, ask, or stop entirely.

**Format:** Bullet list. Each rule names a specific trigger condition and the action to take.

**Rules:**
- This section is the second most commonly under-specified — give it real conditions
- Cover at least: (1) an abstain condition (when the model lacks sufficient information to proceed), (2) a clarification condition (when to ask rather than proceed), and (3) a failure condition (when to report a problem rather than attempt a response)
- Actions must be named: ask, stop, abstain, flag, retry, escalate — not just "stop"
- Conditions must be specific — "if confused" is not a condition

**Example:**
```
# Stop rules
- If the session contains no prompt/response pairs, stop and return: "Session data is empty — no evaluation can be performed."
- If fewer than two dimensions have scoreable signals, abstain from producing a score summary and ask the instructor to verify the session was captured correctly.
- If the session data contains personally identifiable student information beyond an anonymized ID, stop and flag: "PII detected — review before analysis."
- Do not ask for clarification more than once per session evaluation — if the second attempt also lacks sufficient data, return the abstain message.
```

**Anti-patterns:**
- "Stop if unsure" — not a specific condition
- Missing abstain condition — almost every task needs one
- Stop rules that describe normal task behavior rather than exception handling

---

## Anti-Patterns Summary

| Anti-Pattern | Problem | Fix |
|---|---|---|
| Vague role ("helpful assistant") | No behavioral signal | Name the function and context |
| Process goal ("help users with X") | No recognizable success state | Name the deliverable |
| Single success criterion | Under-specified | Minimum 2 binary criteria |
| Aspirational constraints ("try to avoid") | Not enforceable | Rewrite as hard limits |
| Missing stop rules | Model will attempt impossible tasks | Add abstain + clarification + failure conditions |
| Personality in constraints | Wrong section | Move tone instructions to `# Personality` |
| Output format in personality | Wrong section | Move structure specs to `# Output` |
