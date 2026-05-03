import re
import shutil
import time
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Project, Checkpoint
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


@router.get("/projects/{project_id}/events")
def get_project_events(project_id: int, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    checkpoints = (
        db.query(Checkpoint)
        .filter_by(project_id=project_id)
        .order_by(Checkpoint.created_at)
        .all()
    )

    events: list[dict] = []
    seen = {c.task_name for c in checkpoints}
    for c in checkpoints:
        # Worker checkpoints are implementation details and not top-level board tasks.
        if c.task_name.startswith("generate_worker_"):
            continue
        events.append({"task": c.task_name, "type": "started"})
        events.append({"task": c.task_name, "type": "completed"})

    ordered_tasks = ["clarify", "architect", "generate", "review", "fix"]
    if p.status == "running":
        for task in ordered_tasks:
            if task not in seen:
                events.append({"task": task, "type": "started"})
                break
    elif p.status == "done":
        events.append({"task": "done", "type": "done", "workspace": f"workspace/{p.slug}"})
    elif p.status == "paused":
        events.append({"task": "review", "type": "paused", "message": "Run paused for review"})
    elif p.status == "failed":
        events.append({"task": "review", "type": "failed", "message": "Run failed"})
    elif p.status == "stalled":
        events.append({"task": "generate", "type": "failed", "message": "LM Studio call timed out"})

    return events

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


@router.post("/projects/{project_id}/resume")
def resume_project(project_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    if p.status not in ("stalled", "paused"):
        raise HTTPException(status_code=409, detail=f"Cannot resume a project with status '{p.status}'")
    p.status = "running"
    db.commit()
    background_tasks.add_task(_run, p.id, p.slug, p.spec_text, p.active_model, db)
    return {"id": p.id, "status": "running"}
