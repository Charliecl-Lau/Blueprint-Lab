# Blueprint Lab

Blueprint Lab is a controlled research platform for prompt-engineering experiments on undergraduate engineering assessment generation. It prioritizes reproducibility, experimental control, provenance, and research usability.

## Research guarantees

Each immutable run records its condition and run number, ordered source-document bindings, canonical model settings, exact prompt and hash, untouched provider response and hash, parsed assessment, provider metadata, sanitized errors, and generated Word artifact and hash. Retrying a completed or failed run creates the next run number and never overwrites the original evidence.

Hashes use SHA-256. Source and artifact hashes cover exact stored bytes; output hashes cover the exact UTF-8 provider response; prompt hashes cover canonical JSON containing the system and final prompts, prompt structure and versions, model settings, and source hashes in binding order.

## Stage boundaries

Stage 1 provides immutable source snapshots, reproducible generation runs, provenance retrieval, compatibility APIs, and DOCX export. Stage 2 evaluation is intentionally deferred: rubric scoring, reviewer workflows, inter-rater analysis, aggregate comparisons, and statistical reporting are not part of the current generation pipeline.

## Technology

- FastAPI, SQLAlchemy, Pydantic, PostgreSQL, and Alembic
- Celery and Redis progress events
- React, TypeScript, Vite, and Zustand
- `python-docx`, `pypdf`, pytest, and Vitest

## Local setup

Copy `.env.example` to `.env`, install dependencies, create the PostgreSQL database, and apply migrations. The research migration runs online because it uses Python canonical JSON serialization to preserve legacy evidence hashes; offline `alembic --sql` mode is unsupported.

```powershell
python -m pip install -r backend/requirements.txt
$env:DATABASE_URL = "postgresql+psycopg://blueprint:blueprint@localhost:5432/blueprint_lab"
python -m alembic upgrade head
python -m uvicorn backend.main:app --reload
```

Run Redis and the Celery worker using the same environment, then start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173`; the API runs at `http://localhost:8000`.

## Sources and canonical run APIs

Source uploads accept UTF-8 text, Markdown, JSON, DOCX, and unencrypted PDF files up to 20 MiB. Exact bytes are retained independently from extracted prompt text.

```text
POST /source-documents
GET  /source-documents/{id}
GET  /source-documents/{id}/download
POST /conditions/{condition_id}/runs
GET  /runs/{run_id}
POST /runs/{run_id}/retry
GET  /runs/{run_id}/export-docx
```

`GET /runs/{run_id}` excludes raw provider output by default. In the current single-user research deployment, pass `include_raw_response=true` for provenance retrieval.

The deprecated `/generations/{id}`, `/generations/{id}/regenerate`, and generation export routes remain temporary compatibility aliases. New clients should use `/runs`; compatibility regeneration is immutable and returns the newly created run ID.

## Verification

SQLite unit and workflow tests run by default. Set `TEST_POSTGRES_DATABASE_URL` to enable PostgreSQL migration and constraint integration tests; otherwise those tests report an explicit skip reason.

```powershell
python -m pytest backend/tests -v
python -m alembic check
cd frontend
npm test -- --run
npm run build
```

To verify a fresh PostgreSQL database, point `DATABASE_URL` at an empty test database and run `python -m alembic upgrade head` before the suite.

## License

MIT
