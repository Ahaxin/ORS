import json
from sqlalchemy.orm import Session
from backend.models import Checkpoint

class CheckpointManager:
    def __init__(self, db: Session):
        self.db = db

    def save(self, project_id: int, task_name: str, model_used: str, output: dict):
        ck = Checkpoint(
            project_id=project_id,
            task_name=task_name,
            model_used=model_used,
            output_json=json.dumps(output),
        )
        self.db.add(ck)
        self.db.commit()

    def load(self, project_id: int, task_name: str) -> dict | None:
        ck = (
            self.db.query(Checkpoint)
            .filter_by(project_id=project_id, task_name=task_name)
            .order_by(Checkpoint.created_at.desc())
            .first()
        )
        return json.loads(ck.output_json) if ck else None

    def load_all(self, project_id: int) -> list[dict]:
        cks = (self.db.query(Checkpoint)
               .filter_by(project_id=project_id)
               .order_by(Checkpoint.created_at).all())
        return [{"task": c.task_name, "model": c.model_used, "output": json.loads(c.output_json)} for c in cks]
