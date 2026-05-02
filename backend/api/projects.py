import re
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Project
from backend.providers.router import ProviderRouter
from backend.orchestrator.checkpoint import CheckpointManager
from backend.orchestrator.supervisor import Supervisor
from pydantic import BaseModel

router = APIRouter()

class ProjectCreate(BaseModel):
    spec: str

def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()[:40]).strip("-")

async def _run(project_id: int, slug: str, spec: str, db: Session):
    r = ProviderRouter.from_config_file()
    ckpt = CheckpointManager(db)
    await Supervisor(project_id, slug, spec, r, ckpt).run()

@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    r = ProviderRouter.from_config_file()
    slug = _slugify(body.spec)
    p = Project(slug=slug, spec_text=body.spec, status="running", active_model=r.active_model)
    db.add(p); db.commit(); db.refresh(p)
    # Pass _run directly — FastAPI BackgroundTasks handles async coroutines natively.
    # Do NOT wrap with asyncio.run(); it cannot nest inside FastAPI's running event loop.
    background_tasks.add_task(_run, p.id, slug, body.spec, db)
    return {"id": p.id, "slug": p.slug, "status": p.status}

@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    return [{"id": p.id, "slug": p.slug, "status": p.status, "active_model": p.active_model}
            for p in db.query(Project).all()]

@router.get("/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"id": p.id, "slug": p.slug, "status": p.status,
            "active_model": p.active_model, "pending_model": p.pending_model}
