from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Project
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
