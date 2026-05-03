import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.models import Base, Project
from backend.orchestrator.checkpoint import CheckpointManager
from backend.orchestrator.supervisor import Supervisor


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def project(db):
    p = Project(slug="test-app", spec_text="Build a todo app", status="running", active_model="lmstudio")
    db.add(p); db.commit()
    return p


def make_supervisor(db, project, tmp_path):
    router = MagicMock()
    provider = MagicMock()
    provider.concurrency = 2
    provider.timeout_seconds = 60
    router.get_provider.return_value = provider
    router.active_model = "lmstudio"
    router.apply_pending = MagicMock()
    ckpt = CheckpointManager(db)
    import backend.workspace_manager as wm_module
    wm_module.WORKSPACE_ROOT = tmp_path
    sup = Supervisor(project.id, project.slug, project.spec_text, router, ckpt)
    return sup, ckpt


@pytest.mark.asyncio
async def test_run_worker_saves_checkpoint(db, project, tmp_path):
    """Calls the real _run_worker (not patched) — patches only CrewAI internals."""
    sup, ckpt = make_supervisor(db, project, tmp_path)

    mock_result = MagicMock()
    mock_result.raw = "=== FILE: src/a.tsx ===\ncontent"

    assert ckpt.load(project.id, "generate_worker_0") is None

    with patch("backend.orchestrator.supervisor.Crew") as MockCrew, \
         patch("backend.orchestrator.supervisor.make_file_writer"), \
         patch("backend.orchestrator.supervisor.build_generate_chunk_task"):
        MockCrew.return_value.kickoff.return_value = mock_result
        await sup._run_worker(0, [{"path": "src/a.tsx", "description": "A"}], "spec", timeout_seconds=30)

    saved = ckpt.load(project.id, "generate_worker_0")
    assert saved is not None
    assert saved["output"] == "=== FILE: src/a.tsx ===\ncontent"
    assert saved["files"] == ["src/a.tsx"]


@pytest.mark.asyncio
async def test_resume_skips_completed_worker(db, project, tmp_path):
    sup, ckpt = make_supervisor(db, project, tmp_path)

    # Pre-seed worker 0 checkpoint
    ckpt.save(project.id, "generate_worker_0", "lmstudio", {
        "output": "=== FILE: src/a.tsx ===\ncached",
        "files": ["src/a.tsx"]
    })

    file_list = [
        {"path": "src/a.tsx", "description": "A"},
        {"path": "src/b.tsx", "description": "B"},
    ]

    called_workers = []

    async def fake_worker(worker_id, files, spec, timeout_seconds):
        called_workers.append(worker_id)
        return f"=== FILE: {files[0]['path']} ===\nnew"

    with patch.object(sup, "_run_worker", side_effect=fake_worker):
        sup.router.get_provider.return_value.concurrency = 2
        result = await sup._run_generate(file_list, "spec text")

    # Worker 0 was cached; only worker 1 should have been called
    assert 0 not in called_workers
    assert 1 in called_workers
    assert "cached" in result


@pytest.mark.asyncio
async def test_run_log_written_after_clarify(db, project, tmp_path):
    sup, ckpt = make_supervisor(db, project, tmp_path)

    # Pre-seed all checkpoints so only log behaviour is tested
    ckpt.save(project.id, "clarify", "lmstudio", {"refined_spec": "todo app spec"})
    ckpt.save(project.id, "architect", "lmstudio", {"plan": '{"files": []}'})
    ckpt.save(project.id, "generate", "lmstudio", {"files_content": ""})
    ckpt.save(project.id, "review", "lmstudio", {"result": "PASS"})

    with patch.object(sup, "emit", new=AsyncMock()):
        await sup.run()

    log_path = tmp_path / project.slug / "_ors" / "run_log.txt"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "CLARIFY" in content
    assert "ARCHITECT" in content
