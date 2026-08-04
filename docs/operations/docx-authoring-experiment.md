# DOCX authoring experiment operations

## Scope and safety posture

The self-hosted code authoring path is an experiment, not the production default. Keep `DOCX_GENERATION_BACKEND=legacy` in every environment except the approved experiment environment. Enable `self_hosted_code` only after the database migration and sandbox checks below pass.

The sandbox must be reachable only over a private network or a loopback-bound reverse proxy. Set a strong `DOCX_SANDBOX_SERVICE_TOKEN`; never expose the service directly to the public internet. Pin both `DOCX_SANDBOX_SERVICE_IMAGE` and `DOCX_SANDBOX_JOB_IMAGE_DIGEST` to immutable registry digests and configure the backend's `DOCX_SANDBOX_EXPECTED_IMAGE_DIGEST` to the same job digest.

The future OpenAI-hosted authoring provider is only an adapter direction. It is not implemented or selected by this rollout. There is no token threshold, automatic model change, or Option B fallback.

## Reproducible runtime

- Build the service and job images from the checked-in Dockerfiles and locked Python requirements. Record the resulting registry digests in the release evidence.
- Pin LibreOffice to the approved release in the verifier host image and set `DOCX_RENDER_EXPECTED_VERSION` to its reported version fragment.
- Install and record the approved font package versions. Use UTF-8, the `C.UTF-8` locale, UTC, and deterministic Python settings.
- The experiment compose file constrains CPU, memory, process count, timeout, concurrency, output size, read-only filesystems, capabilities, and network binding.
- Completed idempotency results are retained in service memory for `DOCX_SANDBOX_COMPLETED_JOB_RETENTION_SECONDS`; database attempts, hashes, token usage, and validation evidence remain immutable according to the application retention policy.
- Monitor `/health`; it returns the service version and configured job image digest. Treat a mismatch, failed probe, or unexpected digest as a rollout stop.

The free-tier Gemini terms and data-use treatment may differ from paid or enterprise service and can change. Re-check the current provider policy before every live experiment. Do not submit sensitive, regulated, confidential, or student-identifying source material unless the institution's policy and provider agreement explicitly permit it.

## Migration rehearsal

1. Snapshot a non-production database restored from representative production data.
2. Deploy application code with `DOCX_GENERATION_BACKEND=legacy`.
3. Run `alembic upgrade head` and record the starting revision, ending revision, duration, and row counts for runs, assessments, artifacts, model-call usage, and authoring attempts.
4. Verify every existing run still points to its original assessment and exports its legacy artifact.
5. Rehearse rollback of application traffic by disabling new runs. Preserve the upgraded database and all authoring evidence; do not downgrade while experiment evidence is under review.

## Sandbox security acceptance

Run the checked-in sandbox tests and hostile corpus before enabling the flag. The corpus must cover imports, network access, subprocesses, filesystem traversal, dynamic execution, encoded payloads, excessive memory/CPU/process use, symlink output, macros, malformed OOXML, extra output files, and oversized output. Record the image digests and the pass/fail result. A security-policy rejection may be retried only as a wholly new authoring cycle; the rejected program is never repaired or executed again.

Reference-PDF uploads are intentionally not retained as document bytes. A failed upload-backed run therefore exposes original recovery but not rewrite-only retry; create a new run and upload the approved PDFs again. This preserves the data-minimization contract and avoids silently reconstructing incomplete grounding.

## Token experiment

Persisted evidence is read without making model calls:

```powershell
python -m backend.scripts.run_docx_token_experiment --run-id 123 --output C:\tmp\docx-run-123.json
```

CSV is available with `--format csv`. A live retry is deliberately explicit and only accepts an existing `rewrite_failed` run:

```powershell
python -m backend.scripts.run_docx_token_experiment --run-id 123 --execute-live --output C:\tmp\docx-run-123-live.json
```

Reports contain provider/model/version, tokens by stage and attempt, authoring/sandbox/render duration evidence, grounding size/hash, artifact size/page count, validation outcome, and repair use. They exclude prompts, source content, generated code, raw logs, document bytes, and secrets. `decision` is always `null`; an operator makes the workflow decision.

## Page-by-page release acceptance

For one representative, policy-approved course package:

1. Enable `self_hosted_code` only in the non-production experiment environment and create one live run.
2. Save the JSON token report beside the run ID, application image digest, service image digest, job image digest, provider model version, and migration evidence.
3. Download only the verified canonical DOCX. Render it with the pinned LibreOffice build to numbered page images.
4. Inspect every page for clipping, overlap, table wrapping, equations, glyphs, figure placement, headers, footers, and page breaks. Compare section order and visible structure with `docs/docx-design-contract/v1/contract.json`.
5. Record one row per page: page number, pass/fail, deviations, reviewer, timestamp, and evidence image path. Record an overall pass only after every page passes or deviations are explicitly accepted.
6. Verify the UI shows version 2 as `Canonical LLM rewrite`, grading IDs belong to version 2, and export resolves to its verified artifact.
7. Force a terminal rewrite failure and verify version 1 remains immutable, visible as the original recovery version, and has no rewrite artifact or grading access.

Automated render validation is production evidence, but it must never be described as human visual inspection.

## Rollout and rollback

Enable new runs in a narrow operator window with concurrency set to one or two. Stop new runs immediately on security, digest, data-policy, migration, or visual-acceptance failure. Roll back by restoring `DOCX_GENERATION_BACKEND=legacy` and disabling new experiment runs; do not delete runs, attempts, programs, usage, manifests, artifacts, validation reports, or token reports. Existing successful canonical rewrites and failed-run recovery evidence remain inspectable.
