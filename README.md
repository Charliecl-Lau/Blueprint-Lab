# Blueprint

An AI-powered assessment generator that creates structured question sets from curriculum topics. Teachers specify a topic, difficulty, and framework (e.g. Bloom's Taxonomy), and Blueprint generates a full assessment with answer keys exportable to PDF.

## Features

- Generate assessments from a topic, grade level, and learning framework
- Real-time progress streaming via Server-Sent Events (SSE)
- PDF export for both student and answer key variants
- Regenerate individual assessments without re-running the full pipeline
- Celery-backed async worker with idempotent retry support

## Tech Stack

- **Backend:** FastAPI, SQLAlchemy, Celery, Redis
- **Frontend:** React, TypeScript, Vite
- **AI:** LLM-based multi-stage generation pipeline (plan → validate → generate)
- **Export:** WeasyPrint for PDF rendering

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Redis (for Celery broker)

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Start the Celery worker:

```bash
celery -A backend.celery_app worker --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173` and the API at `http://localhost:8000`.

## Project Structure

```
backend/
  api/          # FastAPI route handlers
  models/       # SQLAlchemy ORM models
  schemas/      # Pydantic request/response schemas
  services/     # LLM pipeline: planner, validator, generator
  workers/      # Celery task definitions
frontend/
  src/
    pages/      # InputPanelPage, ProgressPage, AssessmentViewerPage
    api/        # API client functions
    store/      # Zustand run store
    hooks/      # useSSE and other hooks
```

## License

MIT
