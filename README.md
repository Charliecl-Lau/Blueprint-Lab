# Blueprint Lab

Blueprint Lab is a controlled research platform for prompt-engineering experiments on undergraduate engineering assessment generation. It prioritizes reproducibility, experimental control, provenance, and research usability.

## Research guarantees

Each immutable run records its condition and run number, ordered source-document bindings, canonical model settings, the exact Structure System Prompt call, the raw Actual Prompt, the Actual-Prompt-controlled Generation call, untouched provider responses and hashes, parsed assessment, provider metadata, sanitized errors, generated Word artifact and hash, and normalized rubric evaluations. Retrying generation creates the next run number and never overwrites the original evidence. Evaluation-only retries preserve the saved assessment and repeat only missing or failed LLM evaluation work.

Hashes use SHA-256. Source and artifact hashes cover exact stored bytes; output hashes cover the exact UTF-8 provider response. The Actual Prompt hash covers the Structure System Prompt, deterministic first-call input, raw Actual Prompt, structure and versions, and canonical model settings. The Generation envelope hash covers the raw Actual Prompt, exact ordered source context, the same model settings, and source hashes in binding order.

## Stage boundaries

Generation has two model-call stages. The Structure stage receives Assessment Details and Prompt Design Factors but no uploaded source content, and returns a raw provider-specific Actual Prompt. The Generation stage uses that unmodified Actual Prompt as its controlling system instruction and receives ordered immutable source snapshots separately. After the assessment is validated and saved, the Viewer becomes available and the saved questions are passed unchanged to the configured LLM evaluator. The run becomes complete only after rubric evaluations and the Word artifact are saved. Human reviews are stored independently from LLM evaluations, and comparison is available only after human finalization.

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
- A Google AI API key with access to the configured Gemini model

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
LLM_MODEL=gemini-3.1-flash-lite
LLM_EVALUATION_MODEL=
LLM_TEMPERATURE=0.2
LLM_MAX_OUTPUT_TOKENS=32768
LOCAL_REVIEWER_ID=local-reviewer
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

Apply all database migrations before starting the API or worker:

```powershell
python -m alembic upgrade head
python -m alembic current
```

`alembic current` should report `20260717_01 (head)`. Existing databases retain null usage aggregates for legacy runs so the UI can distinguish **Not recorded** from a measured zero. The research migrations must run online because they use Python canonical JSON serialization to preserve legacy evidence hashes; offline `alembic --sql` mode is unsupported.

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

Complete the experiment form and select **Run Experiment**. A successful local flow creates the experiment in PostgreSQL, queues generation through Redis, executes it in Celery, calls the configured generation and evaluation models, and displays persisted progress in the frontend. As soon as validation succeeds, **View Assessment** opens the saved question while evaluation continues. The Viewer refreshes evaluation status and the token total through the run progress stream; **Grade Assessment** becomes available after the LLM evaluation is finalized.

If a run fails, check the Celery terminal first for provider, model-access, or parsing errors. Configuration changes in `.env` require restarting both the backend and Celery. Create a new experiment after changing model settings because existing runs retain their original settings for reproducibility.

Leaving a progress page closes only that browser's live progress connection; it does not cancel Celery work. You can start another experiment while earlier runs continue, then use **Recent runs** to reopen active or completed persisted state. Each run keeps its own status, result, errors, and API-reported token usage by run ID.

The grading page places the collapsed, read-only LLM evaluation before the expanded human rubric form so automated feedback is available without being prominent. Human drafts save on completed-field blur and periodically while dirty. Finalization requires all five scores, locks the review, and enables a neutral human/LLM comparison. `LOCAL_REVIEWER_ID` identifies the reviewer in the current single-user deployment; changing it creates a separate reviewer record instead of overwriting an existing review.

The form validates all required assessment fields and content for each enabled prompt factor before sending a request. Incomplete submissions show a grouped dialog and inline accessible errors, and create no experiment, run, or Celery task. Repeated valid submissions use an idempotency key so a retried request does not enqueue duplicate work.

See [Run Lifecycle and Token Accounting](docs/RUN_LIFECYCLE_AND_TOKEN_ACCOUNTING.md) for the accounting definitions, retry behavior, legacy display, and isolation contract. `LLM_EVALUATION_MODEL` optionally separates evaluation from generation; when blank, evaluation uses `LLM_MODEL`.

## Sources and canonical run APIs

Source uploads accept UTF-8 text, Markdown, JSON, DOCX, and unencrypted PDF files up to 20 MiB. Exact bytes are retained independently from extracted prompt text.

```text
POST /source-documents
GET  /source-documents/{id}
GET  /source-documents/{id}/download
POST /conditions/{condition_id}/runs
GET  /runs/{run_id}
GET  /runs/recent
GET  /runs/{run_id}/progress
POST /runs/{run_id}/retry
GET  /runs/{run_id}/export-docx
POST /assessments/{assessment_id}/evaluations/llm/retry
GET  /assessment-questions/{question_id}/grading-context
GET  /assessments/{assessment_id}/evaluations
POST /assessment-questions/{question_id}/evaluations/human
PATCH /evaluations/{evaluation_id}
POST /evaluations/{evaluation_id}/finalize
POST /evaluations/{evaluation_id}/reopen
POST /evaluations/{evaluation_id}/llm-access
GET  /assessment-questions/{question_id}/evaluation-comparison
```

`GET /runs/{run_id}` returns both stages' hashes, versions, request IDs, model metadata, finish reasons, and durations, while excluding raw instructions, source context, and provider output by default. In the current single-user research deployment, pass `include_raw_response=true` to retrieve the exact Structure System Prompt, first-call input, raw Actual Prompt, Generation context, and assessment response.

The deprecated `/generations/{id}`, `/generations/{id}/regenerate`, and generation export routes remain temporary compatibility aliases. New clients should use `/runs`; compatibility regeneration is immutable and returns the newly created run ID.

## Verification

SQLite unit and workflow tests run by default. Set `TEST_POSTGRES_DATABASE_URL` to enable PostgreSQL migration and constraint integration tests; otherwise those tests report an explicit skip reason.

```powershell
python -m pytest backend/tests -v
python -m pytest backend/tests/test_end_to_end_run_lifecycle.py -v
python -m alembic check
cd frontend
npm test -- --run
npm run lint
npm run build
```

To verify a fresh PostgreSQL database, point `DATABASE_URL` at an empty test database and run `python -m alembic upgrade head` before the suite.

## License

MIT
