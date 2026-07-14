from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.api.experiments import router as experiments_router
from backend.api.generations import router as generations_router
from backend.api.runs import router as runs_router
from backend.api.source_documents import router as source_documents_router
from backend.services.experiment_service import (
    ExperimentValidationError,
    validation_issues_from_request_errors,
)

app = FastAPI(title="Blueprint Lab")


@app.exception_handler(RequestValidationError)
async def structured_experiment_request_errors(
    request: Request, exc: RequestValidationError
):
    if request.method == "POST" and request.url.path.rstrip("/") == "/experiments":
        issues = validation_issues_from_request_errors(exc.errors())
        return JSONResponse(
            status_code=422,
            content={"detail": {"errors": [issue.to_dict() for issue in issues]}},
        )
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(ExperimentValidationError)
async def structured_experiment_service_errors(
    request: Request, exc: ExperimentValidationError
):
    return JSONResponse(
        status_code=422,
        content={"detail": {"errors": [issue.to_dict() for issue in exc.issues]}},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(experiments_router)
app.include_router(generations_router)
app.include_router(runs_router)
app.include_router(source_documents_router)

@app.get("/health")
def health():
    return {"status": "ok"}
