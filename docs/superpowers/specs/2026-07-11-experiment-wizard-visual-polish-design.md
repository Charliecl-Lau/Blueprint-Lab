# Experiment Wizard Visual Polish

**Date:** 2026-07-11
**Scope:** `frontend/src/pages/InputPanelPage.tsx`, `frontend/src/index.css`

## Context

The New Experiment wizard's left sidebar, step navigation buttons, and run action bar diverge visually from the reference mockup (`image.png`). This is a CSS/markup polish pass — no behavior or data changes.

## Changes

### 1. Left sidebar nav (`.wizard-nav`)
- Remove the boxed icon background (`.step-icon` grey square with border-radius). Icons render flush next to the label text instead of looking like a separate button.
- Widen nav items: increase `.wizard-nav` width from 250px and increase button horizontal padding so labels have more breathing room, matching the reference's wider selection rows.
- Remove the grey subtitle `<small>` text currently rendered under each label (`item.subtitle`).
- Add a small green dot indicator on the right side of each nav item when that section is complete. "Complete" = the section's required fields currently pass validation (derived from existing `validate()` logic per section, computed without mutating `errors` state — e.g. a lightweight per-section completeness check).

### 2. Previous / Next buttons (`.section-navigation button`)
- Remove border (`border: 1px solid #d2d2d7` → none).
- Reduce font size (from inherited ~14px to ~13px).
- Remove hover background-color change (`.section-navigation button:hover { background: #fff; border-color: #e2e2e5; }` is dropped).

### 3. Run action bar (`.fixed-run-action`)
- Change background from `rgba(255,255,255,.96)` (white) to match the page's grey background (`#f5f5f7`), so the pill blends into the page instead of floating as a white card. Keep the "Run Experiment" button itself unchanged (blue background, white text).

## Out of scope
- No changes to validation logic, routing, or API calls.
- No changes to `PromptFactorFields` component internals.
- No color change to the Run Experiment button itself.
