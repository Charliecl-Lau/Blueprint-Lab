# Generation Progress Indicator Implementation Plan

## Goal

Make long-running assessment and Word document generation visibly active without using a spinner, fabricated percentage, or indeterminate progress bar.

## Scope

The progress page will combine three signals:

1. A stable label describing the current persisted stage.
2. A contextual activity sentence that rotates every 10 seconds.
3. An elapsed-time display calculated from the server-provided run start time.

## Implementation

### 1. Extend the run progress contract

- Return `started_at` from the run-detail API and progress stream snapshots.
- Add the optional timestamp to the backend response schema and frontend `Run` type.
- Preserve `null` for queued runs that have not started.

### 2. Define stage-specific activity messages

- Map every non-terminal run stage to concise, truthful messages.
- Rotate messages every 10 seconds.
- Reset to the first message whenever the persisted stage changes.
- Do not rotate messages in completed, warning, rewrite-failed, or error states.

### 3. Display elapsed time

- Calculate elapsed time from `started_at`, not page-load time.
- Update it once per second and format it as seconds, minutes and seconds, or hours and minutes.
- Stop updating when the run reaches a terminal state or the page unmounts.
- Fall back to `Working` if no server start time is available.

### 4. Update progress-page presentation

Present the current state in this order:

- Stable stage label
- Rotating contextual activity sentence
- `Working · <duration> elapsed`
- Reassurance that work continues in the background

After two minutes, replace the standard reassurance with a message explaining that complex assessments may take several minutes. Do not add a spinner, progress percentage, or progress bar.

### 5. Accessibility

- Announce changing activity sentences through a polite atomic live region.
- Keep the ticking elapsed-time value outside the live region.
- Retain visible text for terminal and recovery states.

### 6. Tests and verification

- Verify the backend exposes stable and nullable `started_at` values.
- Test initial and rotating messages, stage-change resets, elapsed-time formatting, the two-minute reassurance, terminal-state behavior, and the missing-timestamp fallback.
- Run the focused backend and frontend tests, the frontend build, and broader relevant suites.

## Acceptance criteria

An active run always shows a stable stage, changing contextual wording, and accurate server-based elapsed time. The timer survives refreshes without resetting, all activity stops in terminal states, and no spinner or invented completion percentage is shown.
