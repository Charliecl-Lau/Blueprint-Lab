from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.experiments import router as experiments_router
from backend.api.generations import router as generations_router
from backend.database import Base, engine
import backend.models.experiment  # noqa: F401

app = FastAPI(title="Blueprint Lab")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(experiments_router)
app.include_router(generations_router)


@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}
