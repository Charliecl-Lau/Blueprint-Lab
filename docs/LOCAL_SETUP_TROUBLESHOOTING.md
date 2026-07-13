# Local Setup Troubleshooting and Blueprint Transfer Notes

This runbook records the problems encountered while bringing Blueprint Lab up locally on Windows. Use it when rebuilding the environment or moving the fixes back to the upstream Blueprint repository.

## Known-good local stack

- PostgreSQL 16 in Docker on `localhost:5432`
- Redis 7 in Docker on `localhost:6379`
- FastAPI on `http://localhost:8000`
- Celery 5.4 using the Windows `solo` pool
- Vite frontend on `http://localhost:5173`
- Google Gemini API using `gemma-4-31b-it`

The setup and application fixes are in commit `5097014` (`Fix and document local generation setup`).

## Safe environment setup

### Symptom

The application has missing configuration, or a real Google API key is at risk of being committed in `.env.example`.

### Root cause

`.env.example` is a tracked template. Runtime secrets belong in `.env`, which is ignored by Git.

### Fix

```powershell
Copy-Item .env.example .env
```

Set the real key only in `.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://blueprint:blueprint@localhost:5432/blueprint_lab
REDIS_URL=redis://localhost:6379/0
GOOGLE_API_KEY=replace-with-real-key
LLM_PROVIDER=google
LLM_MODEL=gemma-4-31b-it
LLM_TEMPERATURE=0.2
```

Before committing, confirm `.env.example` does not contain a real key and `.env` is ignored:

```powershell
git check-ignore .env
git diff -- .env.example
```

## Empty `LLM_SEED` prevents startup

### Symptom

Pydantic reports a validation error for `llm_seed` while loading settings.

### Root cause

The template contained `LLM_SEED=`. An empty string cannot be parsed as the optional integer expected by `backend/config.py`.

### Fix

Remove the empty `LLM_SEED=` line from `.env`. Add it only when an integer seed is required:

```dotenv
LLM_SEED=42
```

### Verification

```powershell
python -c "from backend.config import settings; print(settings.llm_seed)"
```

The command should print `None` when no seed is configured.

## Docker database and Redis services

### Symptom

PostgreSQL or Redis connections fail because the command-line clients are unavailable or Docker Desktop is not running.

### Root cause

The local machine did not have standalone PostgreSQL tools installed. Docker was available, but its daemon had to be started before containers could run.

### Fix

Start Docker Desktop, then create the containers once:

```powershell
docker run -d --name blueprint-lab-postgres -e POSTGRES_USER=blueprint -e POSTGRES_PASSWORD=blueprint -e POSTGRES_DB=blueprint_lab -p 5432:5432 postgres:16
docker run -d --name blueprint-lab-redis -p 6379:6379 redis:7
```

On later sessions:

```powershell
docker start blueprint-lab-postgres blueprint-lab-redis
```

### Verification

```powershell
docker ps
docker exec blueprint-lab-redis redis-cli ping
```

Redis should return `PONG`.

## Fresh database migration failure

### Symptom

Running `python -m alembic upgrade head` against a new database fails with:

```text
psycopg.errors.UndefinedTable: relation "generations" does not exist
```

### Root cause

The only Alembic revision, `20260711_01_research_foundation.py`, is a legacy-data migration. It expects the old `generations` and related tables to exist and is not a fresh-schema bootstrap migration.

### Current fresh-database procedure

Create the current SQLAlchemy schema, then stamp the database at the migration head:

```powershell
python -c "import backend.models; from backend.database import Base, engine; Base.metadata.create_all(bind=engine)"
python -m alembic stamp head
python -m alembic current
```

Expected revision:

```text
20260711_01 (head)
```

For a database that already contains the legacy pre-research schema, use the actual migration:

```powershell
python -m alembic upgrade head
```

### Blueprint transfer concern

The metadata-and-stamp procedure is a local bootstrap workaround, not a replacement for a proper baseline migration. Before production deployment, add a fresh-schema baseline or otherwise formalize how empty and legacy databases take separate upgrade paths.

## Frontend Run Experiment button appeared inactive

### Symptom

Selecting **Run Experiment** caused no visible navigation or backend generation. Backend logs showed repeated responses like:

```text
POST /api/experiments HTTP/1.1 404 Not Found
```

### Root cause

The frontend API client intentionally sends requests to `/api`. Vite proxied those paths to FastAPI without removing the prefix, while FastAPI registers `/experiments`, not `/api/experiments`.

### Fix

Configure the Vite proxy to remove `/api`:

```ts
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      rewrite: (path) => path.replace(/^\/api/, ''),
    },
  },
},
```

Affected files:

- `frontend/vite.config.ts`
- `frontend/src/viteProxy.test.ts`

### Verification

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:5173/api/health
```

The response should be HTTP 200 with `{"status":"ok"}`. An intentionally incomplete POST to `/api/experiments` should reach FastAPI as `/experiments` and return validation status 422 rather than route status 404.

## Google generation failed with model 404

### Symptom

The experiment was created and Celery received the task, but the run failed with:

```text
models/gemma-4-31b is not found for API version v1beta,
or is not supported for generateContent
```

### Root cause

The model identifier omitted its instruction-tuned suffix. The supported hosted Gemma model is `gemma-4-31b-it`.

### Fix

Change the model in all defaults and templates:

```dotenv
LLM_MODEL=gemma-4-31b-it
```

Affected files:

- `.env.example`
- `backend/config.py`
- `backend/tests/test_database_config.py`
- `backend/tests/test_llm_client.py`

Restart FastAPI and Celery after editing `.env`; both load settings at process startup. Create a new experiment because existing runs preserve their original model settings.

### Verification

Use the configured key to confirm model visibility without printing the key:

```powershell
python -c "from google import genai; from backend.config import settings; names={m.name.removeprefix('models/') for m in genai.Client(api_key=settings.google_api_key).models.list()}; print(settings.llm_model in names)"
```

The command should print `True`.

## Starting all application services on Windows

Open separate PowerShell windows at the repository root.

Backend:

```powershell
python -m uvicorn backend.main:app --reload
```

Celery:

```powershell
python -m celery -A backend.celery_app worker --loglevel=info --pool=solo
```

Frontend:

```powershell
Set-Location frontend
npm run dev
```

The `solo` pool avoids Windows worker-process compatibility problems.

### Health checks

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8000/health
Invoke-WebRequest -UseBasicParsing http://localhost:5173
docker exec blueprint-lab-redis redis-cli ping
python -m celery -A backend.celery_app inspect ping --timeout=10
```

Expected results are HTTP 200 for the API and frontend, `PONG` from Redis, and one Celery node returning `pong`.

## Known unresolved issue: Celery retries are not idempotent

### Symptom

After the provider rejected the invalid model, Celery retried the same task. Later attempts failed with:

```text
duplicate key value violates unique constraint "prompts_run_id_key"
Key (run_id)=(1) already exists
```

### Root cause

`run_generation_pipeline` creates and commits a `Prompt` before calling the provider. On retry, the task starts from the beginning and tries to create another prompt for the same run, but `prompts.run_id` is unique.

### Status

This issue was diagnosed but not fixed in commit `5097014`. Successful provider calls are unaffected, but transient provider or artifact failures may not retry cleanly.

### Recommended future fix

Make each pipeline stage resume-safe:

1. Load the existing prompt for the run before creating one.
2. Create a prompt only when none exists.
3. Reuse stored prompt text and hash on provider retries.
4. Apply the same idempotency rule to assessment and document artifact records.
5. Add a regression test that forces a provider failure on the first attempt and succeeds on retry without duplicate records.

Do not remove the uniqueness constraints to hide the problem; they protect the one-prompt, one-assessment, and one-artifact evidence model.

## Verification suite

Run before transferring or merging the fixes:

```powershell
python -m pytest backend/tests -q
python -m alembic current
Set-Location frontend
npm test -- --run
npm run build
```

The last verified results during setup were:

- Backend: 66 passed, 3 PostgreSQL integration tests skipped
- Frontend: 15 passed
- Frontend production build: passed
- Alembic: `20260711_01 (head)`

## Moving the fixes back to Blueprint

1. Compare Blueprint's current API route prefixes and Vite proxy before applying the proxy change.
2. Port or cherry-pick commit `5097014` if the target branch shares compatible files.
3. Keep secrets out of the commit; transfer only `.env.example`, never `.env`.
4. Confirm the target Google project can list `gemma-4-31b-it`.
5. Decide whether the target database is empty or contains the legacy schema before running Alembic.
6. Run the full backend and frontend verification suites.
7. Perform one new experiment through `http://localhost:5173` and confirm this sequence in logs:
   - `POST /experiments` returns 200.
   - Celery receives `run_generation_pipeline`.
   - The provider call succeeds.
   - The run reaches `complete`.
   - The generated assessment and DOCX artifact are available.
8. Fix the retry-idempotency issue before relying on automatic retries in production.

