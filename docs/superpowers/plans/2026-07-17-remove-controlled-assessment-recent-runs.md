# Remove Controlled Assessment Recent Runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Recent Runs section from the controlled-assessment input page without changing scrolling or layout behavior.

**Architecture:** Keep the reusable `RecentRuns` component and its CSS intact, but stop composing it into `InputPanelPage`. Lock the behavior with an application-level rendering test that supplies recent-run data and confirms the page does not expose the Recent Runs region.

**Tech Stack:** React 19, TypeScript, React Testing Library, Vitest

## Global Constraints

- Do not change viewport sizing, overflow, scrolling, navigation, form behavior, or the fixed Run Experiment action.
- Leave `frontend/src/components/RecentRuns.tsx` and the `.recent-runs` CSS rules unchanged.
- Preserve the independent top-right `RunProgressShortcut` behavior.

---

### Task 1: Remove Recent Runs from the controlled-assessment page

**Files:**
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/pages/InputPanelPage.tsx`

**Interfaces:**
- Consumes: `InputPanelPage()` as the `/` route rendered by `App`.
- Produces: A controlled-assessment page that does not render a region labelled `Recent runs`.

- [ ] **Step 1: Replace the obsolete reopen-list test with a failing absence test**

In `frontend/src/App.test.tsx`, replace `test('recent active run reopens run-specific progress', ...)` with:

```tsx
test('does not render the Recent Runs section on the controlled-assessment page', async () => {
  vi.mocked(fetch).mockImplementation(async (input) => {
    if (String(input).includes('/api/runs/recent?limit=')) {
      return {
        ok: true,
        json: async () => ([{
          id: 8,
          experiment_id: 1,
          condition_id: 3,
          run_number: 1,
          status: 'generating',
          topic: 'Equilibrium',
          condition_label: 'Baseline',
          created_at: '2026-07-14T00:00:00Z',
          completed_at: null,
          token_usage: {
            input_tokens: 10,
            output_tokens: 4,
            total_tokens: 14,
            model_calls: 1,
            recording_state: 'in_progress',
            stages: [],
          },
        }]),
      } as Response
    }
    return { ok: true, json: async () => ({ id: 42, conditions: [], runs: [] }) } as Response
  })

  render(<App />)

  await screen.findByRole('link', { name: 'Return to run progress: Equilibrium' })
  expect(screen.queryByRole('heading', { name: 'Recent runs' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /Reopen run/ })).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run from `frontend`:

```powershell
npm test -- --run src/App.test.tsx -t "does not render the Recent Runs section"
```

Expected: FAIL because the current `InputPanelPage` renders the `RecentRuns` component and exposes the `Recent runs` heading and reopen link.

- [ ] **Step 3: Remove the Recent Runs composition from `InputPanelPage`**

In `frontend/src/pages/InputPanelPage.tsx`, delete this import:

```tsx
import { RecentRuns } from '../components/RecentRuns'
```

Delete this rendered element below `.wizard-layout`:

```tsx
<RecentRuns />
```

Do not modify any surrounding markup or CSS.

- [ ] **Step 4: Run the focused test and verify it passes**

Run from `frontend`:

```powershell
npm test -- --run src/App.test.tsx -t "does not render the Recent Runs section"
```

Expected: PASS.

- [ ] **Step 5: Run the complete frontend checks**

Run from `frontend`:

```powershell
npm test -- --run
npm run build
```

Expected: All Vitest tests pass, TypeScript compilation succeeds, and the Vite production build completes.

- [ ] **Step 6: Commit the implementation**

```powershell
git add -- frontend/src/App.test.tsx frontend/src/pages/InputPanelPage.tsx
git commit -m "Remove recent runs from assessment input" -m "Stop rendering the Recent Runs list beneath the controlled-assessment wizard so the page can be evaluated without that extra content. Preserve the reusable component, progress shortcut, and all existing scrolling and layout behavior."
```

