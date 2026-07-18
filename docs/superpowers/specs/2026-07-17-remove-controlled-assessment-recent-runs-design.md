# Remove Controlled Assessment Recent Runs

## Goal

Remove the Recent Runs section from the controlled-assessment input page so the user can evaluate the page's existing scrolling behavior without that additional content.

## Scope

- Stop rendering `RecentRuns` from `InputPanelPage`.
- Remove the now-unused `RecentRuns` import from that page.
- Leave the reusable `RecentRuns` component and its styles unchanged because this request only removes it from the controlled-assessment page.
- Do not change viewport sizing, overflow, scrolling, navigation, form behavior, or the fixed Run Experiment action.

## Verification

- Update or add a frontend test confirming the controlled-assessment page does not render the Recent Runs heading when recent-run data is available.
- Run the focused frontend test suite for the page.

