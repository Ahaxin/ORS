import pytest
from unittest import mock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from backend.models import Base, Project
from backend.database import get_db
from backend.main import app, reset_orphaned_running_projects


@pytest.fixture
def client():
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


@pytest.fixture
def stalled_project(client):
    res = client.post("/projects", json={"spec": "Build a todo app"})
    pid = res.json()["id"]
    db = next(client.app.dependency_overrides[get_db]())
    p = db.get(Project, pid)
    p.status = "stalled"
    db.commit()
    return pid


@pytest.fixture
def paused_project(client):
    res = client.post("/projects", json={"spec": "Build a blog"})
    pid = res.json()["id"]
    db = next(client.app.dependency_overrides[get_db]())
    p = db.get(Project, pid)
    p.status = "paused"
    db.commit()
    return pid


def test_resume_stalled_project(client, stalled_project):
    res = client.post(f"/projects/{stalled_project}/resume")
    assert res.status_code == 200
    assert res.json()["status"] == "running"


def test_resume_paused_project(client, paused_project):
    res = client.post(f"/projects/{paused_project}/resume")
    assert res.status_code == 200
    assert res.json()["status"] == "running"


def test_resume_not_found(client):
    res = client.post("/projects/9999/resume")
    assert res.status_code == 404


def test_resume_running_project_returns_409(client):
    res = client.post("/projects", json={"spec": "Build a shop"})
    pid = res.json()["id"]
    db = next(client.app.dependency_overrides[get_db]())
    p = db.get(Project, pid)
    p.status = "running"
    db.commit()
    res = client.post(f"/projects/{pid}/resume")
    assert res.status_code == 409


def test_resume_done_project_returns_409(client):
    res = client.post("/projects", json={"spec": "Build a dashboard"})
    pid = res.json()["id"]
    db = next(client.app.dependency_overrides[get_db]())
    p = db.get(Project, pid)
    p.status = "done"
    db.commit()
    res = client.post(f"/projects/{pid}/resume")
    assert res.status_code == 409


def test_resume_failed_project_returns_409(client):
    res = client.post("/projects", json={"spec": "Build a CRM"})
    pid = res.json()["id"]
    db = next(client.app.dependency_overrides[get_db]())
    p = db.get(Project, pid)
    p.status = "failed"
    db.commit()
    res = client.post(f"/projects/{pid}/resume")
    assert res.status_code == 409


def test_startup_resets_running_to_stalled(client):
    res = client.post("/projects", json={"spec": "Build a thing"})
    pid = res.json()["id"]
    db = next(client.app.dependency_overrides[get_db]())
    p = db.get(Project, pid)
    p.status = "running"
    db.commit()

    reset_orphaned_running_projects(db)
    db.refresh(p)
    assert p.status == "stalled"
