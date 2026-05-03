import re
import shutil
import time
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Project
from backend.providers.router import ProviderRouter
from backend.orchestrator.checkpoint import CheckpointManager
from backend.orchestrator.supervisor import Supervisor
from backend.workspace_manager import WorkspaceManager
from pydantic import BaseModel

router = APIRouter()

class ProjectCreate(BaseModel):
    spec: str
    model: str | None = None

def _slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()[:40]).strip("-")
    return f"{base}-{int(time.time())}"

async def _run(project_id: int, slug: str, spec: str, active_model: str, db: Session):
    r = ProviderRouter.from_config_file()
    r.active_model = active_model
    ckpt = CheckpointManager(db)
    await Supervisor(project_id, slug, spec, r, ckpt).run()

@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    r = ProviderRouter.from_config_file()
    if body.model:
        r.active_model = body.model
    slug = _slugify(body.spec)
    p = Project(slug=slug, spec_text=body.spec, status="running", active_model=r.active_model)
    db.add(p); db.commit(); db.refresh(p)
    # Pass _run directly — FastAPI BackgroundTasks handles async coroutines natively.
    # Do NOT wrap with asyncio.run(); it cannot nest inside FastAPI's running event loop.
    background_tasks.add_task(_run, p.id, slug, body.spec, r.active_model, db)
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

@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    if p.status == "running":
        raise HTTPException(status_code=409, detail="Cannot delete a running project")
    slug = p.slug
    workspace_root = WorkspaceManager(slug).root
    if workspace_root.exists():
        shutil.rmtree(workspace_root)
    db.delete(p)
    db.commit()
