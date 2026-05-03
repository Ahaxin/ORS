import pytest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.models import Base, Project, Checkpoint
from backend.workspace_manager import WorkspaceManager
import backend.workspace_manager as wm_module

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

def test_workspace_write_read_list(tmp_path, monkeypatch):
    monkeypatch.setattr(wm_module, "WORKSPACE_ROOT", tmp_path)
    mgr = WorkspaceManager("my-app")
    mgr.write_file("src/index.ts", "export default {}")
    assert mgr.read_file("src/index.ts") == "export default {}"
    assert "src/index.ts" in mgr.list_files()

def test_write_json(tmp_path, monkeypatch):
    monkeypatch.setattr(wm_module, "WORKSPACE_ROOT", tmp_path)
    mgr = WorkspaceManager("my-app")
    mgr.write_json("_ors/clarify.json", {"refined_spec": "a todo app"})
    raw = (tmp_path / "my-app" / "_ors" / "clarify.json").read_text()
    assert json.loads(raw)["refined_spec"] == "a todo app"

def test_write_text(tmp_path, monkeypatch):
    monkeypatch.setattr(wm_module, "WORKSPACE_ROOT", tmp_path)
    mgr = WorkspaceManager("my-app")
    mgr.write_text("_ors/generate.md", "=== FILE: src/app.ts ===\nconsole.log(1)")
    content = (tmp_path / "my-app" / "_ors" / "generate.md").read_text()
    assert "console.log(1)" in content
