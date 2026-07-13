# Railway Worker and Frontend Deployment Design

## Goal

Deploy Blueprint Lab's Celery worker and React frontend into the existing Railway project while keeping the FastAPI API, worker, PostgreSQL, and Redis private. Users access one public frontend domain, and Caddy forwards browser requests under `/api/*` to FastAPI over Railway private networking.

## Services

- `Blueprint-Lab`: existing private FastAPI service, listening on a fixed internal port and retaining `/health` plus normal Alembic pre-deploy migrations.
- `worker`: private Celery service built from the repository-root Python Dockerfile. It shares the API's PostgreSQL, Redis, Google API, and model configuration, overrides the image command with `python -m celery -A backend.celery_app worker --loglevel=info`, and has no public domain or HTTP health check.
- `frontend`: public service built from `/frontend`. A multi-stage Dockerfile builds the Vite application and serves `dist` with Caddy.
- Existing Railway PostgreSQL and Redis services remain private dependencies.

## Frontend Routing

Caddy listens on Railway's injected `PORT`. Requests under `/api/*` are stripped of the `/api` prefix and reverse-proxied to the FastAPI service's private hostname and fixed port. All other requests serve static assets, with `index.html` fallback for React Router. `/health` returns a direct success response for Railway health checks.

This preserves the frontend's existing `/api` fetch, download, and EventSource URLs and avoids cross-origin browser traffic or production CORS changes.

## Deployment Configuration

The frontend receives a committed `frontend/Dockerfile` and `frontend/Caddyfile`. The backend Dockerfile remains the shared image definition for the API and worker. Railway service configuration selects the appropriate root directory, Dockerfile, start command, variables, health check, and domain for each service.

The API uses a fixed `PORT=8000` so Caddy has a stable private upstream. PostgreSQL uses the explicit SQLAlchemy `postgresql+psycopg://` URL assembled from Railway references; Redis uses Railway's Redis URL. The worker receives matching values so queued runs observe the same configuration as the API.

## Failure Handling

- Caddy returns an upstream error if FastAPI is unavailable; its own `/health` remains available to distinguish frontend-container failure from API failure.
- Celery logs provider, database, or broker failures through Railway logs and follows Railway's restart-on-failure policy.
- Alembic remains an API pre-deploy responsibility and is not run by the worker, avoiding concurrent migration attempts.
- The worker and API remain single-replica initially to limit duplicate task-processing and research-cost risk.

## Verification

Before deployment:

- Build the frontend production bundle.
- Build the frontend Docker image.
- Validate the Caddy configuration.
- Run existing frontend tests and relevant backend worker tests.

After deployment:

- Confirm API, worker, and frontend deployments report success.
- Confirm the worker connects to Redis and becomes ready.
- Confirm the frontend public `/health` returns HTTP 200.
- Confirm frontend `/api/health` proxies to FastAPI and returns `{"status":"ok"}`.
- Confirm a React client-side route falls back to `index.html`.

An end-to-end generation is deferred until the Google API key is rotated and a supported model is confirmed, preventing deliberate use of the exposed temporary key.
