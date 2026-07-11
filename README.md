# Blueprint Lab

Blueprint Lab is a controlled research platform for prompt-engineering experiments on undergraduate engineering assessment generation. It prioritizes reproducibility, experimental control, metadata logging, and research usability over production flexibility.

## Research workflow

```text
Prompt Generation -> Question Generation -> Word Document Generation -> Metadata Logging -> Persistence
```

Researchers configure course context, assessment requirements, estimated student completion time, a fixed provider prompt structure, and independently selectable prompt design factors. Every condition records the exact factor content, generated prompt, model metadata, generated questions, and Word artifact.

Prompt design factors include Concept Bridge, Few-shot Examples, Reference Content, and Reasoning Guidance. Reasoning Guidance requests concise visible rationale or structured solution steps; it does not request or expose hidden private model reasoning.

## Technology

- FastAPI, SQLAlchemy, Pydantic
- Celery and Redis progress events
- React, TypeScript, Vite, Zustand
- `python-docx` Word generation
- pytest and Vitest

## Development

Install backend dependencies and run the API from the repository root:

The migration uses PostgreSQL's `pgcrypto` extension for reproducible SHA-256
backfills. The migration installs it with `CREATE EXTENSION IF NOT EXISTS`; the
migration role must be allowed to install the extension if it is not present.

```powershell
python -m pip install -r backend/requirements.txt
$env:DATABASE_URL = "postgresql+psycopg://blueprint:blueprint@localhost:5432/blueprint_lab"
python -m alembic upgrade head
python -m uvicorn backend.main:app --reload
```

Run the worker and Redis using the project’s configured environment. Then start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173`; the API runs at `http://localhost:8000`.

## Verification

```powershell
python -m pytest backend/tests -v
cd frontend
npm test -- --run
npm run build
```

## License

MIT
