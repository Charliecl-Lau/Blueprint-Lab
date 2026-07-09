from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.runs import router as runs_router
from backend.api.assessments import router as assessments_router
from backend.database import Base, engine
import backend.models.run  # noqa: F401
import backend.models.assessment  # noqa: F401
import backend.models.question  # noqa: F401

app = FastAPI(title="Assessment Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router)
app.include_router(assessments_router)


@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}
