# Railway Worker and Frontend Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a private Celery worker and a public Caddy-served React frontend into the existing Railway project without disrupting the working FastAPI API.

**Architecture:** The worker uses a dedicated repository-root Dockerfile with the same Python dependencies as the API image and a Celery-specific command, selected through Railway's `RAILWAY_DOCKERFILE_PATH` variable. The frontend uses a Node build stage and Caddy runtime stage; Caddy serves the SPA and strips `/api` before proxying to FastAPI on Railway private networking.

**Tech Stack:** Railway CLI 5.26.0, Docker, Python 3.12, Celery, React 19, Vite 8, Node 22, Caddy 2

## Global Constraints

- Keep `Blueprint-Lab`, PostgreSQL, Redis, and `worker` private; only `frontend` receives a public domain.
- Set the API's fixed internal port to `8000` and proxy to its Railway private hostname.
- Preserve the frontend's existing `/api` URLs and strip that prefix at Caddy.
- Do not run Alembic from the worker; migrations remain the API pre-deploy responsibility.
- Run one API replica and one worker replica initially.
- Do not run an end-to-end generation until the Google API key is rotated and the configured Google model is confirmed supported.
- Every commit has a subject and explanatory paragraph body, with no attribution trailers.

---

### Task 1: Production frontend container

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/Caddyfile`
- Create: `frontend/.dockerignore`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: Railway's `PORT` environment variable and an `API_UPSTREAM` value in `host:port` form.
- Produces: An HTTP service with direct `GET /health`, SPA fallback, and `/api/*` reverse proxying with the `/api` prefix removed.

- [ ] **Step 1: Run the existing frontend test suite as a baseline**

Run: `npm test -- --run`

Working directory: `frontend`

Expected: Vitest exits successfully with the existing component, store, and proxy tests passing.

- [ ] **Step 2: Add the production Docker build**

Create `frontend/Dockerfile`:

```dockerfile
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM caddy:2-alpine

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
```

- [ ] **Step 3: Add same-origin proxy and SPA routing**

Create `frontend/Caddyfile`:

```caddyfile
{
	admin off
	auto_https off
}

:{$PORT:3000} {
	handle /health {
		respond "ok" 200
	}

	handle_path /api/* {
		reverse_proxy {$API_UPSTREAM:blueprint-lab.railway.internal:8000}
	}

	handle {
		root * /srv
		encode zstd gzip
		try_files {path} /index.html
		file_server
	}
}
```

- [ ] **Step 4: Keep build-only files out of the Docker context**

Create `frontend/.dockerignore`:

```text
node_modules
dist
.git
*.log
```

- [ ] **Step 5: Build and validate the frontend artifacts**

Run: `npm run build`

Working directory: `frontend`

Expected: TypeScript and Vite complete successfully and create `frontend/dist`.

Run: `docker build -t blueprint-lab-frontend:local .`

Working directory: `frontend`

Expected: Docker completes both stages and tags `blueprint-lab-frontend:local`.

Run: `docker run --rm blueprint-lab-frontend:local caddy validate --config /etc/caddy/Caddyfile`

Expected: Caddy reports `Valid configuration` and exits successfully.

- [ ] **Step 6: Commit the frontend container**

```powershell
git add frontend/Dockerfile frontend/Caddyfile frontend/.dockerignore
git commit -m "Add Railway frontend container" -m "Build the Vite application in a reproducible Node stage and serve it with Caddy. The runtime configuration provides a Railway health endpoint, SPA fallback, and same-origin API proxying over private networking."
```

### Task 2: Railway API and worker configuration

**Files:**
- Create: `Dockerfile.worker`
- Runtime configuration only: Railway project `Blueprint Lab`, services `Blueprint-Lab` and `worker`

**Interfaces:**
- Consumes: existing Railway PostgreSQL, Redis, Google provider, and model variables.
- Produces: API on private port `8000` and one Celery worker connected to the same database and broker.

- [ ] **Step 1: Pin and verify the API's private port**

Run: `railway variable set PORT=8000 --service Blueprint-Lab`

Run: `railway redeploy --service Blueprint-Lab --yes`

Expected: The new API deployment reaches `SUCCESS`, and deploy logs show Uvicorn listening on `0.0.0.0:8000`.

- [ ] **Step 2: Run the worker tests before creating the service**

Run: `python -m pytest backend/tests/test_worker.py -q`

Expected: The worker pipeline tests pass without calling the external Google API.

- [ ] **Step 3: Create the private worker service without a source**

Run: `railway add --service worker --json`

Expected: Railway creates an empty `worker` service in the production environment without starting a deployment.

- [ ] **Step 4: Add and validate the worker-specific Dockerfile**

Create `Dockerfile.worker`:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt

RUN pip install --no-cache-dir -r backend/requirements.txt

COPY alembic.ini alembic.ini
COPY backend backend

CMD ["python", "-m", "celery", "-A", "backend.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
```

Run: `docker build -f Dockerfile.worker -t blueprint-lab-worker:local .`

Expected: Docker completes successfully and tags `blueprint-lab-worker:local`.

Run: `docker image inspect blueprint-lab-worker:local --format '{{json .Config.Cmd}}'`

Expected: `["python","-m","celery","-A","backend.celery_app","worker","--loglevel=info","--concurrency=2"]`.

- [ ] **Step 5: Configure the worker Dockerfile and shared variables**

Run:

```powershell
railway variable set --service worker --skip-deploys 'RAILWAY_DOCKERFILE_PATH=Dockerfile.worker' 'DATABASE_URL=postgresql+psycopg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}' 'REDIS_URL=${{Redis.REDIS_URL}}' 'GOOGLE_API_KEY=${{Blueprint-Lab.GOOGLE_API_KEY}}' 'LLM_PROVIDER=${{Blueprint-Lab.LLM_PROVIDER}}' 'LLM_MODEL=${{Blueprint-Lab.LLM_MODEL}}' 'LLM_TEMPERATURE=${{Blueprint-Lab.LLM_TEMPERATURE}}' 'LLM_TOP_P=${{Blueprint-Lab.LLM_TOP_P}}' 'LLM_MAX_OUTPUT_TOKENS=${{Blueprint-Lab.LLM_MAX_OUTPUT_TOKENS}}' --json
```

Do not configure a pre-deploy command, HTTP health check, or public domain.

Expected: Railway resolves the database and Redis references inside the worker without exposing their values in the committed repository.

- [ ] **Step 6: Commit the worker Dockerfile and fallback documentation**

```powershell
git add Dockerfile.worker docs/superpowers/plans/2026-07-13-railway-worker-frontend-deployment.md
git commit -m "Add Railway worker container" -m "Provide a Celery-specific Dockerfile that Railway can select through its documented Dockerfile-path variable. This avoids the CLI start-command editor that no-ops for the new worker while keeping its deployment reproducible from GitHub."
git push origin main
```

- [ ] **Step 7: Deploy and inspect worker readiness**

Run: `railway service source connect --service worker --repo Charliecl-Lau/Blueprint-Lab --branch main --json`

Expected: Deployment status reaches `SUCCESS`; logs show Celery connected to Redis and ready, with registered assessment tasks and no crash loop.

### Task 3: Railway frontend and live routing verification

**Files:**
- Reuse: `frontend/Dockerfile`
- Reuse: `frontend/Caddyfile`
- Runtime configuration only: Railway service `frontend`

**Interfaces:**
- Consumes: the API private hostname through `API_UPSTREAM`.
- Produces: one Railway public HTTPS domain serving both the React SPA and proxied API requests.

- [ ] **Step 1: Create and configure the frontend service**

Run: `railway add --service frontend --repo Charliecl-Lau/Blueprint-Lab --branch main --json`

Run:

```powershell
railway environment edit --service-config frontend source.rootDirectory '/frontend' --service-config frontend deploy.healthcheckPath '/health' --message 'Configure the public frontend Docker service' --json
```

Run: `railway variable set --service frontend --skip-deploys 'API_UPSTREAM=blueprint-lab.railway.internal:8000' --json`

Leave the start command unset so the image uses Caddy's default command. Railway detects `frontend/Dockerfile` from the configured root directory.

Expected: Railway builds `frontend/Dockerfile` from the frontend directory and checks the Caddy endpoint on its injected port.

- [ ] **Step 2: Deploy the frontend and create its public domain**

Run: `railway redeploy --service frontend --yes`

Run: `railway domain --service frontend`

Expected: Deployment reaches `SUCCESS`, and Railway returns a public `*.up.railway.app` domain for `frontend` only.

- [ ] **Step 3: Verify direct and proxied health endpoints**

Run:

```powershell
$domain = (railway domain list --service frontend --json | ConvertFrom-Json | Where-Object { $_.type -eq 'service' } | Select-Object -First 1).domain
curl.exe -fsS "https://$domain/health"
```

Expected: HTTP success with body `ok`.

Run: `curl.exe -fsS "https://$domain/api/health"`

Expected: HTTP success with JSON body `{"status":"ok"}`.

- [ ] **Step 4: Verify SPA fallback**

Run: `curl.exe -fsS "https://$domain/progress"`

Expected: HTTP success containing the built application's `<div id="root"></div>` markup.

- [ ] **Step 5: Perform final service checks**

Run: `railway status --json`

Expected: `Blueprint-Lab`, `worker`, and `frontend` latest deployments report `SUCCESS`; PostgreSQL and Redis remain available; no public domain exists on the worker.

Review recent API, worker, and frontend logs without displaying secret variables. Expected: no startup traceback, worker broker disconnect, Caddy upstream resolution error, or health-check failure.
