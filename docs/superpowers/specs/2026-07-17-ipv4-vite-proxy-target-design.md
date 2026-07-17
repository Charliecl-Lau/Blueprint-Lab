# IPv4 Vite API Proxy Target Design

## Problem

The frontend sends API requests to `/api`, and Vite forwards those requests to the FastAPI development server. The proxy currently targets `http://localhost:8000`. On Windows, Node can resolve `localhost` to the IPv6 loopback address (`::1`) while Uvicorn is listening on the IPv4 loopback address (`127.0.0.1`). In that state, FastAPI remains healthy when called directly, but Vite returns a gateway error because it cannot connect to the resolved target.

The runtime investigation also found stale API processes sharing port 8000. Those processes caused the earlier HTTP 500 behavior, but process cleanup alone does not make the proxy target deterministic. Once the stale processes were removed, the IPv4/IPv6 mismatch reproduced consistently as an HTTP 502 through Vite.

## Decision

Set the Vite development proxy target explicitly to `http://127.0.0.1:8000`.

This keeps the browser-facing API path unchanged, matches the documented Uvicorn bind address, and avoids operating-system-specific `localhost` resolution. The backend host, API routes, payloads, database schema, Celery configuration, and production deployment remain unchanged.

## Alternatives Considered

1. Bind Uvicorn only to `::1`. This would make the current Node resolution work, but direct IPv4 clients would fail and local setup would remain dependent on address-family behavior.
2. Bind the backend to all interfaces. This would accept more connection paths but unnecessarily broadens local network exposure and does not address deterministic loopback configuration.
3. Continue using `localhost` and restart services when resolution fails. This is not durable and would allow the same failure to return after process or DNS-order changes.

The explicit IPv4 target is the smallest and most predictable change.

## Data Flow

1. The browser sends a request such as `POST /api/experiments` to Vite on port 5173.
2. Vite removes the `/api` prefix using the existing rewrite rule.
3. Vite forwards the request to `http://127.0.0.1:8000/experiments`.
4. FastAPI validates and processes the request using the existing experiment workflow.

No response transformation or new retry behavior is introduced.

## Error Handling

Existing frontend and backend error handling remains authoritative. If the backend is not running on `127.0.0.1:8000`, Vite will continue returning a gateway error, which correctly signals a missing local dependency. The change only eliminates incorrect routing to an IPv6 loopback address.

The historical condition 10, run 1 record is outside this fix. Its task is no longer present in Celery and should not be requeued automatically because it predates the current submission and may incur a new model call. A new valid experiment submission should create a new run after the proxy is repaired.

## Testing

Update the existing Vite proxy regression test to require `http://127.0.0.1:8000` and preserve the `/api` prefix rewrite assertion. The test must fail against the current `localhost` configuration before the configuration changes.

After implementation:

- run the focused Vite proxy test;
- run the frontend test suite and production build;
- verify FastAPI health directly through `127.0.0.1:8000`;
- verify an idempotent, non-enqueuing experiment POST through `localhost:5173/api/experiments` returns HTTP 200.

## Scope

This change is limited to the local Vite development proxy and its regression test. It does not modify experiment persistence, worker recovery, retry semantics, model calls, or historical run data.
