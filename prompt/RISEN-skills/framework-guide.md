# RISEN Framework — Section-by-Section Guide

Source: medium.com/@tahirbalarabe2/prompt-engineering-made-simple-with-the-risen-framework-038d98319574

This file defines how each of the five RISEN sections should be written, what each one is for, and what to avoid. Read this before generating any prompt.

---

## Core Design Philosophy

The RISEN framework is built on one analogy: a prompt is a recipe. A recipe doesn't just say "make a cake" — it specifies ingredients, steps, cooking time, and presentation. Without structure, you get a burnt mess. Without a structured prompt, you get a rambling, unfocused AI response.

Three principles govern all five sections:

**1. Specificity over vagueness.** Every section should be specific enough that the AI has no ambiguity to fill in. If two users could reasonably interpret a section differently, rewrite it.

**2. Show, don't just tell.** The Examples section exists because AI learns from patterns. A single concrete input-output pair does more work than three paragraphs of instruction.

**3. Balance control and flexibility.** Over-constraining with too many rules in Nuance can confuse the AI. Curate your constraints — include only those that materially change the output.

---

## Section Rules

### **Role** — Define the AI's Expertise

**Job:** Assign a specific persona, expertise level, and audience awareness to the AI. This adjusts depth, tone, and perspective before the AI reads anything else.

**Format:** 1–2 sentences. Name the expertise domain and the audience or context.

**Rules:**
- Name a specific role with a relevant domain — not a generic "assistant"
- Include the intended audience if it affects depth or vocabulary ("explaining to a non-technical audience" changes everything)
- Do not include task instructions here — that belongs in Instruction
- Avoid inflated or decorative roles ("world-class genius") that add no behavioral signal

**Strong example:**
```
Role: You are a senior Python developer specializing in web scraping, explaining your approach to a junior developer.
```

**Weak example:**
```
Role: You are a helpful and knowledgeable AI assistant.
```
Why weak: No specific domain, no audience, no perspective — the AI's behavior is unchanged.

**Strong example (Forge context):**
```
Role: You are a learning analytics researcher specializing in AI-assisted education, explaining workflow scoring methodology to an instructor with no data science background.
```

---

### **Instruction** — Be Painfully Specific

**Job:** State exactly what the AI must produce. Specific, actionable, testable.

**Format:** 2–4 sentences or a numbered list. Lead with an action verb. Name the deliverable.

**Rules:**
- Lead with an action verb: Write, Analyze, Generate, Compare, Identify, Produce, Summarize
- Name the deliverable explicitly — what the user receives, not what the AI internally does
- Include scope constraints in the instruction if they affect the task (word count, number of items, time period)
- If the AI tends to ignore a critical part, restate it in emphasis: "IMPORTANT: Do not exceed 300 words"
- One instruction block per prompt — if there are two separate tasks, write two prompts

**Strong example:**
```
Instruction: Write a 500-word blog post titled "5 Science-Backed Productivity Hacks for Remote Workers." Use subheadings for each hack, include one supporting statistic per section, and end with a 2-sentence actionable summary.
```

**Weak example:**
```
Instruction: Write something about productivity for remote workers.
```
Why weak: No length, no structure signal, no scope — the AI fills in every decision arbitrarily.

---

### **Structure** — Control the Format

**Job:** Define how the response is organized and formatted. This is separate from what the response says — it controls how it looks and is navigated.

**Format:** Name the format type, then describe the sections or hierarchy.

**Rules:**
- Name a specific format type: bullet list, numbered list, table, code block, markdown with headers, JSON, prose paragraphs
- If the output has sections, name them and their expected length or content
- Do not say "organize clearly" or "use a logical structure" — name the actual format
- Tables work best for comparisons; code blocks for executable outputs; numbered lists for sequential steps; bullet lists for non-ordered items

**Strong example:**
```
Structure: Format as:
1. Key takeaway (1 sentence)
2. Three supporting points (bullet points, 1–2 sentences each)
3. A recommended action (1 sentence)
```

**Strong example (technical):**
```
Structure: Format as:
- Code block (fully executable, with inline comments)
- Below the code: bullet list of 3–5 key implementation decisions explained in plain English
```

**Weak example:**
```
Structure: Make it easy to read and well-organized.
```
Why weak: No format is specified — "easy to read" is a quality judgment, not a structure instruction.

---

### **Examples** — Show, Don't Just Tell

**Job:** Provide input-output demonstrations that anchor the AI's interpretation of the task. This is few-shot learning — it trains the AI to match your style, depth, and format.

**Format:** One or more input-output pairs. Label them clearly: Input / Output, or Before / After, or Example Input / Example Output.

**Rules:**
- Always include at least one concrete example — do not leave this section as a placeholder or template
- Examples should demonstrate the hardest or most representative case, not the easiest
- The output in the example should match the Structure you specified — they must be consistent
- If tone is critical, the example's output must demonstrate that tone
- More examples = more consistent AI behavior; start with one, add more if outputs vary

**Strong example:**
```
Examples:
Input: "Summarize this tweet: 'AI is transforming healthcare.'"
Output: "AI applications are improving diagnostics and treatment personalization in medicine."
```

**Strong example (Forge context):**
```
Examples:
Input session signal: "Student submitted three prompts with increasing specificity: vague → constrained → structured."
Output label: "IIS: Positive refinement trajectory — prompts became more targeted across iterations."
```

**Weak example:**
```
Examples: [Provide an example here if needed]
```
Why weak: A placeholder is not an example. It provides zero few-shot signal to the AI.

**Advanced:** For complex tasks, provide a negative example (what NOT to produce) alongside the positive one. This tightens the output space significantly.

---

### **Nuance** — Set Boundaries

**Job:** Fine-tune tone, length, style, and exclusions. Nuance is the last layer of precision — it constrains the output space after Role, Instruction, Structure, and Examples have done the heavy work.

**Format:** Bullet list of specific constraints. Each constraint names a dimension and its value.

**Rules:**
- Each constraint must be specific and enforceable: "Under 150 words" not "be concise"; "Avoid jargon unless defined" not "keep it simple"
- Cover at least two dimensions: tone + length is the minimum; add style or exclusion constraints as needed
- Do not repeat constraints already embedded in the Instruction — Nuance is for adjustments, not restatements
- Avoid over-constraining: more than 5–6 nuance rules creates confusion; curate to only what materially changes the output
- Common dimensions: Tone, Length, Audience level, Exclusions ("Avoid X"), Format preference, Language register, Citation style

**Strong example:**
```
Nuance:
- Tone: Professional but approachable — conversational without being casual
- Length: Under 150 words total
- Avoid: Technical jargon unless immediately defined in parentheses
- Audience: Assume no prior knowledge of machine learning
```

**Weak example:**
```
Nuance: Be professional and keep it short. Don't use complicated words.
```
Why weak: No specific lengths, no enforceable tone definition, "complicated words" is undefined.

---

## Anti-Patterns Summary

| Section | Anti-Pattern | Fix |
|---|---|---|
| Role | "You are a helpful assistant" | Name the domain, expertise level, and audience |
| Instruction | "Write something about X" | Name the deliverable, length, and specific scope |
| Structure | "Make it well-organized" | Name the exact format type and section hierarchy |
| Examples | "[Add example here]" or no examples | Always include at least one real input-output pair |
| Nuance | "Be concise and professional" | Specify exact length ("under 150 words") and a defined tone |

---

## Comparison with Other Frameworks

The article positions RISEN relative to two alternatives:

**RTF (Role, Task, Format):** Simple but shallow — lacks Examples and Nuance, so outputs vary unpredictably and tone is uncontrolled.

**CRISPE (Context, Role, Instructions, Style, Personalization, Examples):** Good for creative and tonal control, but complex for everyday and technical use.

**RISEN's position:** Detailed enough for accuracy and repeatability, flexible enough for technical, creative, and business tasks. The Examples section is RISEN's key differentiator — it's the mechanism that shifts AI behavior from rule-following to pattern-matching, which is more reliable for complex outputs.

---

## Advanced Usage

**Chain-of-Thought integration:** Add "Think step-by-step before responding" to the Instruction for complex reasoning tasks. RISEN provides the structure; chain-of-thought improves the reasoning within it.

**Persona blending in Role:** "You are a mix of a data scientist and a technical writer" is a valid RISEN role for outputs that need both precision and readability.

**Negative examples in Examples:** Adding one "Input / Bad Output / Why it's wrong" example alongside the positive example reduces output variance significantly for high-stakes tasks.

**Iterating Nuance:** If the AI ignores a nuance constraint, move it into the Instruction with emphasis ("IMPORTANT: Do not exceed 300 words") — Instruction carries more weight than Nuance.
