# Blueprint Lab

Blueprint Lab is a controlled research platform for prompt-engineering experiments on undergraduate engineering assessment generation. It prioritizes reproducibility, experimental control, provenance, and research usability.

## Research guarantees

Each immutable run records its condition and run number, ordered source-document bindings, canonical model settings, the exact Structure System Prompt call, the raw Actual Prompt, the Actual-Prompt-controlled Generation call, untouched provider responses and hashes, parsed assessment, provider metadata, sanitized errors, and generated Word artifact and hash. Retrying a completed or failed run creates the next run number, repeats both model calls, and never overwrites the original evidence.

Hashes use SHA-256. Source and artifact hashes cover exact stored bytes; output hashes cover the exact UTF-8 provider response. The Actual Prompt hash covers the Structure System Prompt, deterministic first-call input, raw Actual Prompt, structure and versions, and canonical model settings. The Generation envelope hash covers the raw Actual Prompt, exact ordered source context, the same model settings, and source hashes in binding order.

## Stage boundaries

Generation has two model-call stages. The Structure stage receives Assessment Details and Prompt Design Factors but no uploaded source content, and returns a raw provider-specific Actual Prompt. The Generation stage uses that unmodified Actual Prompt as its controlling system instruction and receives ordered immutable source snapshots separately. Both calls use the same model and canonical run settings. Evaluation remains deferred: rubric scoring, reviewer workflows, inter-rater analysis, aggregate comparisons, and statistical reporting are not part of the current pipeline.

## Technology

- FastAPI, SQLAlchemy, Pydantic, PostgreSQL, and Alembic
- Celery and Redis progress events
- React, TypeScript, Vite, and Zustand
- `python-docx`, `pypdf`, pytest, and Vitest

## Local setup

Prerequisites:

- Python 3.9 or newer
- Node.js and npm
- Docker Desktop
- A Google AI API key with access to `gemma-4-31b-it`

Run all commands from the repository root unless a step says otherwise.

### 1. Configure the environment

Copy the environment template, then put your Google API key in `.env`. Do not put a real key in `.env.example`; `.env` is ignored by Git.

```powershell
Copy-Item .env.example .env
```

The relevant values should look like this:

```dotenv
DATABASE_URL=postgresql+psycopg://blueprint:blueprint@localhost:5432/blueprint_lab
REDIS_URL=redis://localhost:6379/0
GOOGLE_API_KEY=replace-with-your-google-api-key
LLM_PROVIDER=google
LLM_MODEL=gemma-4-31b-it
LLM_TEMPERATURE=0.2
```

### 2. Install dependencies

```powershell
python -m pip install -r backend/requirements.txt
Set-Location frontend
npm install
Set-Location ..
```

### 3. Start PostgreSQL and Redis

Start Docker Desktop, then create the local containers. These commands are only needed once:

```powershell
docker run -d --name blueprint-lab-postgres -e POSTGRES_USER=blueprint -e POSTGRES_PASSWORD=blueprint -e POSTGRES_DB=blueprint_lab -p 5432:5432 postgres:16
docker run -d --name blueprint-lab-redis -p 6379:6379 redis:7
```

On later sessions, start the existing containers instead:

```powershell
docker start blueprint-lab-postgres blueprint-lab-redis
```

### 4. Initialize the database

For a new, empty local database, create the current schema and record the Alembic revision:

```powershell
python -c "import backend.models; from backend.database import Base, engine; Base.metadata.create_all(bind=engine)"
python -m alembic stamp head
python -m alembic current
```

`alembic current` should report `20260712_01 (head)`. For a database containing the legacy pre-research schema, run `python -m alembic upgrade head` instead. The research migrations must run online because they use Python canonical JSON serialization to preserve legacy evidence hashes; offline `alembic --sql` mode is unsupported.

### 5. Start the application

Open three PowerShell windows at the repository root.

Backend API:

```powershell
python -m uvicorn backend.main:app --reload
```

Celery worker (the `solo` pool is required on Windows):

```powershell
python -m celery -A backend.celery_app worker --loglevel=info --pool=solo
```

Frontend:

```powershell
Set-Location frontend
npm run dev
```

Open `http://localhost:5173`. The API health endpoint is `http://localhost:8000/health`.

### 6. Run an end-to-end generation

Complete the experiment form and select **Run Experiment**. A successful local flow creates the experiment in PostgreSQL, queues generation through Redis, executes it in Celery, calls the configured Google model, and displays progress and output in the frontend.

If a run fails, check the Celery terminal first for provider, model-access, or parsing errors. Configuration changes in `.env` require restarting both the backend and Celery. Create a new experiment after changing model settings because existing runs retain their original settings for reproducibility.

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

`GET /runs/{run_id}` returns both stages' hashes, versions, request IDs, model metadata, finish reasons, and durations, while excluding raw instructions, source context, and provider output by default. In the current single-user research deployment, pass `include_raw_response=true` to retrieve the exact Structure System Prompt, first-call input, raw Actual Prompt, Generation context, and assessment response.

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
