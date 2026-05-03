import pytest
from unittest import mock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from backend.models import Base, Project
from backend.database import get_db
from backend.main import app

@pytest.fixture
def client():
    # StaticPool ensures all connections share the same in-memory SQLite database.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    def override():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_db] = override
    fake_router = mock.MagicMock()
    fake_router.active_model = "lmstudio"
    with mock.patch("backend.api.projects._run"), \
         mock.patch("backend.api.projects.ProviderRouter.from_config_file", return_value=fake_router):
        yield TestClient(app)
    app.dependency_overrides.clear()

def test_create_project(client):
    res = client.post("/projects", json={"spec": "Build a todo app"})
    assert res.status_code == 201
    data = res.json()
    assert "slug" in data and "id" in data

def test_list_projects(client):
    client.post("/projects", json={"spec": "Build a todo app"})
    res = client.get("/projects")
    assert res.status_code == 200
    assert len(res.json()) == 1

def test_switch_model(client):
    res = client.post("/projects", json={"spec": "Build a todo app"})
    pid = res.json()["id"]
    res = client.put(f"/projects/{pid}/model", json={"model": "openai"})
    assert res.status_code == 200
    assert res.json()["pending_model"] == "openai"

def test_delete_project(client):
    res = client.post("/projects", json={"spec": "Build a blog"})
    pid = res.json()["id"]
    db = next(client.app.dependency_overrides[get_db]())
    p = db.get(Project, pid)
    p.status = "done"
    db.commit()
    res = client.delete(f"/projects/{pid}")
    assert res.status_code == 204

def test_delete_project_not_found(client):
    res = client.delete("/projects/9999")
    assert res.status_code == 404

def test_delete_running_project_returns_409(client):
    res = client.post("/projects", json={"spec": "Build a blog"})
    pid = res.json()["id"]
    db = next(client.app.dependency_overrides[get_db]())
    p = db.get(Project, pid)
    p.status = "running"
    db.commit()
    res = client.delete(f"/projects/{pid}")
    assert res.status_code == 409

def test_delete_removes_from_list(client):
    res = client.post("/projects", json={"spec": "Build a shop"})
    pid = res.json()["id"]
    db = next(client.app.dependency_overrides[get_db]())
    p = db.get(Project, pid)
    p.status = "done"
    db.commit()
    assert client.delete(f"/projects/{pid}").status_code == 204
    projects = client.get("/projects").json()
    assert not any(p["id"] == pid for p in projects)
