from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from backend.database import create_tables, SessionLocal
from backend.models import Project


def reset_orphaned_running_projects(db: Session) -> None:
    db.query(Project).filter(Project.status == "running").update({"status": "stalled"})
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    with SessionLocal() as db:
        reset_orphaned_running_projects(db)
    yield


app = FastAPI(title="ORS", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.api.stream import router as stream_router
from backend.api.projects import router as projects_router
from backend.api.settings import router as settings_router
app.include_router(stream_router)
app.include_router(projects_router)
app.include_router(settings_router)
