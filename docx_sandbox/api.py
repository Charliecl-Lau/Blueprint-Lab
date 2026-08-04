from __future__ import annotations
import hmac
import threading
import time
from typing import Optional
from fastapi import Depends, FastAPI, Header, HTTPException
from .config import SandboxSettings, get_settings
from .contracts import ExecuteRequest, ExecuteResponse, ResultStatus
from .preflight import inspect_program
from .runner import DockerEngine, SandboxRunner

app = FastAPI(title="DOCX Sandbox", version="1")
_lock = threading.Lock(); _completed: dict[str, tuple[float, ExecuteResponse]] = {}; _in_flight = 0

def get_runner(settings: SandboxSettings = Depends(get_settings)) -> SandboxRunner:
    return SandboxRunner(settings, DockerEngine(settings))

def require_auth(authorization: Optional[str] = Header(default=None), settings: SandboxSettings = Depends(get_settings)):
    token = (authorization or "").removeprefix("Bearer ")
    if not settings.service_token or not hmac.compare_digest(token, settings.service_token):
        raise HTTPException(401, "authentication required")

@app.get("/health")
def health(settings: SandboxSettings = Depends(get_settings)):
    return {"status": "ok", "version": settings.service_version, "job_image_digest": settings.job_image_digest}

@app.post("/v1/jobs", response_model=ExecuteResponse, dependencies=[Depends(require_auth)])
def execute(request: ExecuteRequest, runner: SandboxRunner = Depends(get_runner)):
    global _in_flight
    key = str(request.job_id)
    with _lock:
        cutoff = time.monotonic() - runner.settings.completed_job_retention_seconds
        for completed_key, (completed_at, _) in list(_completed.items()):
            if completed_at < cutoff:
                del _completed[completed_key]
        if key in _completed: return _completed[key][1]
    with _lock:
        if _in_flight >= runner.settings.max_concurrency:
            raise HTTPException(429, "sandbox concurrency limit reached")
        _in_flight += 1
    try:
        report = inspect_program(request.program)
        if not report.allowed:
            response = ExecuteResponse(job_id=request.job_id, status=ResultStatus.policy_rejected, evidence={"image_digest": runner.settings.job_image_digest, "wall_time_ms": 0}, issues=[f"{i.code}:{i.line}" for i in report.issues])
        else:
            response = runner.execute(request)
    finally:
        with _lock: _in_flight -= 1
    with _lock: _completed[key] = (time.monotonic(), response)
    return response
