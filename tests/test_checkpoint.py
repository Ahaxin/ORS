import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.models import Base, Project
from backend.orchestrator.checkpoint import CheckpointManager

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s

def test_save_and_load(db):
    p = Project(slug="app", spec_text="todo", status="running", active_model="lmstudio")
    db.add(p); db.commit()
    mgr = CheckpointManager(db)
    mgr.save(project_id=p.id, task_name="clarify", model_used="lmstudio", output={"qa": ["What?", "A todo app"]})
    result = mgr.load(project_id=p.id, task_name="clarify")
    assert result["qa"][0] == "What?"

def test_load_missing_returns_none(db):
    mgr = CheckpointManager(db)
    assert mgr.load(project_id=999, task_name="clarify") is None
