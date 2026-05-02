import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.models import Base, Project, Checkpoint

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def test_create_project(db):
    p = Project(slug="test-app", spec_text="Build a todo app", status="pending", active_model="lmstudio")
    db.add(p)
    db.commit()
    assert db.get(Project, p.id).slug == "test-app"

def test_checkpoint_links_to_project(db):
    p = Project(slug="test-app", spec_text="Build a todo app", status="pending", active_model="lmstudio")
    db.add(p)
    db.commit()
    c = Checkpoint(project_id=p.id, task_name="clarify", model_used="lmstudio", output_json='{"qa": []}')
    db.add(c)
    db.commit()
    assert db.get(Checkpoint, c.id).project_id == p.id
