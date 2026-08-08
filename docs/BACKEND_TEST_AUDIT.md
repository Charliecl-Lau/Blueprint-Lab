# Backend test audit

Audit date: 2026-08-05

## Result

Pytest collects 506 backend cases across 67 files, not 5,000. The test source is
9,840 lines. On the audit machine, 498 tests passed and eight PostgreSQL tests
skipped in 14.10 seconds.

The routine suite is now 497 SQLite-compatible tests. Nine PostgreSQL migration
tests remain available as an explicit integration suite. No tests were deleted:
the suite is already fast, and the audit found no exact duplicate test bodies or
obsolete production subsystem whose tests could be removed safely.

## Coverage by responsibility

| Responsibility | Collected cases | Decision |
| --- | ---: | --- |
| Focused units, prompts, parsing, and utilities | 189 | Keep |
| DOCX generation and verification | 103 | Keep; all four configured backends remain supported |
| Contracts and database models | 74 | Keep |
| API and end-to-end workflows | 70 | Keep |
| Workers and services | 61 | Keep |
| PostgreSQL migrations and constraints | 9 | Keep, run separately |

These groups add to 506. The categories are based on test-file responsibility,
so they are a maintenance inventory rather than a statement-coverage metric.

## Why the remaining tests are useful

- The API and workflow tests protect immutable research evidence, retries,
  idempotency, failure cleanup, and history behavior. Unit tests do not replace
  those cross-layer guarantees.
- Contract tests cover provider-facing structured output and equation handling,
  where individual invalid cases exercise distinct validation branches.
- DOCX tests cover `luna_direct`, `legacy`, `self_hosted_code`, and
  `agentic_tools`. The latter three are not the default, but they are still
  selectable application features.
- Migration tests exercise PostgreSQL-specific DDL, data preservation, and
  constraints that SQLite cannot represent accurately.

## Commands

Routine backend verification:

```powershell
python -m pytest backend/tests -m "not integration" -q
```

PostgreSQL migration verification, using a disposable database:

```powershell
$env:TEST_POSTGRES_DATABASE_URL = "postgresql+psycopg://blueprint:blueprint@localhost:5432/blueprint_lab_test"
python -m pytest backend/tests/integration -m integration -q
```

Full collection without a configured PostgreSQL database (useful for confirming
selection and skip behavior):

```powershell
python -m pytest backend/tests -q
```

## Removal rule for future changes

Delete a test only when its production path is removed, or when another test
exercises the same behavior at the same boundary and fails for the same defect.
Do not use case count alone as a reduction target; collected parameter cases can
represent separate validation branches even when they share one test function.
