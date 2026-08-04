# Agentic DOCX tools operations

The `agentic_tools` backend is an explicit, opt-in Word-generation backend. `legacy` remains the default. Gemini selects a bounded vocabulary of typed layout operations; application code validates those operations, compiles fresh OOXML with `python-docx`, renders it with LibreOffice and Poppler, and accepts it only after machine validation and a Gemini visual approval.

## Enable and roll back

Set `DOCX_GENERATION_BACKEND=agentic_tools` only after applying migration `20260803_01` and validating the configured LibreOffice binary. Roll back by setting only `DOCX_GENERATION_BACKEND=legacy`. Do not downgrade the database after agentic evidence has been recorded.

Resource limits are controlled by `DOCX_TOOL_MAX_REVISIONS`, `DOCX_TOOL_MAX_OPERATIONS_PER_TURN`, `DOCX_TOOL_MAX_REVIEW_PAGES`, `DOCX_TOOL_MAX_REVIEW_IMAGE_BYTES`, and `DOCX_TOOL_MAX_TOTAL_SECONDS`.
Agentic Gemini design and visual-review requests use `DOCX_TOOL_PROVIDER_TIMEOUT_SECONDS` (120 seconds by default), independently of the standard 60-second assessment request timeout.

## Evidence and recovery

Sessions, iterations, validated actions, workspace hashes, render hashes, validator findings, decisions, and separate `docx_tool_design`/`docx_visual_review` usage are retained. Page bytes and temporary paths are never returned by the run API. A failed cycle enters `rewrite_failed`; version 1 and its legacy artifact remain the original recovery document.

Generate a content-free evidence report with:

```powershell
python -m backend.scripts.run_agentic_docx_experiment --run-id 123 --output evidence.json
```

Before rollout, inspect every rendered page and record human acceptance for clipping, hierarchy, typography, tables, native equations, headers, footers, page breaks, and accessibility. The live acceptance record is an operational gate and is not automated by this script.
