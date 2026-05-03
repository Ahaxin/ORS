import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Project
from backend.providers.router import ProviderRouter
from pydantic import BaseModel

router = APIRouter()

class ModelSwitch(BaseModel):
    model: str

@router.put("/projects/{project_id}/model")
def switch_model(project_id: int, body: ModelSwitch, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    p.pending_model = body.model
    db.commit()
    return {"pending_model": p.pending_model, "message": "Switches at next task boundary"}


@router.get("/providers/lmstudio/status")
def lmstudio_status():
    router_cfg = ProviderRouter.from_config_file()
    base_url = router_cfg.config["providers"]["lmstudio"]["base_url"]
    try:
        resp = httpx.get(f"{base_url}/models", timeout=3.0)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if data:
            return {"model": data[0]["id"], "status": "ready"}
        return {"model": None, "status": "unavailable"}
    except httpx.HTTPError:
        return {"model": None, "status": "unavailable"}
