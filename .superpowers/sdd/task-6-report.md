# Task 6 Report

Implemented canonical immutable run creation, retry, retrieval, and DOCX export APIs. Run numbering locks the condition on PostgreSQL, retains the SQLite-compatible unique-constraint path, and retries integrity conflicts up to three times. Retry copies model settings and source-binding snapshots while preserving all evidence on the original run.

Compatibility generation retrieval/export remains available; regenerate now delegates to immutable retry, returns both IDs for the new run, and emits deprecation headers. Experiment creation delegates to `create_run` and exposes both `runs` and `generations`.

Verification:

- Focused: `11 passed`
- Full backend suite: `58 passed, 3 skipped`

Known note: pytest emits an existing `pytest-asyncio` configuration deprecation warning.

## Review follow-up

Retry now carries the exact original source-binding snapshot hash rather than recomputing it from mutable source metadata. Run insertion attempts use nested transactions so allocation conflicts can retry without discarding flushed parent records, while non-conflict failures clean the transaction. Canonical route tests cover create, detail, raw-response opt-in/default exclusion, retry, and export; compatibility tests cover dual experiment keys and immutable regeneration.

- Focused follow-up: `14 passed`
- Full backend follow-up: `61 passed, 3 skipped`
