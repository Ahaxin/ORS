# Checkpoint Resume & Model Output Visibility — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make long ORS runs recoverable after computer hibernation by adding per-worker checkpoints, a timeout on LM Studio calls, a resume endpoint, and a model output log.

**Architecture:** Each generate worker saves its own SQLite checkpoint on completion; a per-worker `asyncio.wait_for` timeout marks the project `stalled` on hang; a `POST /projects/{id}/resume` endpoint re-runs the supervisor which skips already-checkpointed steps and workers. A startup hook resets orphaned `running` projects to `stalled` on server restart. Model output is appended incrementally to `_ors/run_log.txt`.

**Tech Stack:** FastAPI, SQLAlchemy (SQLite), asyncio, pytest, React/TypeScript, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-05-03-checkpoint-resume-design.md`

---

## File Map

| File | Action | What changes |
|---|---|---|
| `config.yaml` | Modify | Add `timeout_minutes: 10` to each provider block |
| `backend/providers/base.py` | Modify | Add `timeout_seconds: int = 600` class attribute |
| `backend/providers/router.py` | Modify | Set `provider.timeout_seconds` from config in `get_provider()` |
| `backend/workspace_manager.py` | Modify | Add `append_text(path, content)` method |
| `backend/main.py` | Modify | Startup hook: reset `running` → `stalled` |
| `backend/api/projects.py` | Modify | Add `POST /projects/{id}/resume` endpoint |
| `backend/orchestrator/supervisor.py` | Modify | Per-worker checkpoints, timeout, log, status writes |
| `frontend/src/api/client.ts` | Modify | Add `resumeProject(id)` |
| `frontend/src/pages/Project.tsx` | Modify | Stalled/paused badge, Resume button, log links |
| `frontend/src/pages/Gallery.tsx` | Modify | Add stalled/paused to `STATUS_COLOR` and polling |
| `tests/test_providers.py` | Modify | Add `timeout_seconds` tests |
| `tests/test_workspace_append.py` | Create | Tests for `append_text()` |
| `tests/test_resume_api.py` | Create | Tests for startup hook + resume endpoint |
| `tests/test_supervisor_resume.py` | Create | Tests for per-worker checkpoints + timeout |

---

## Task 1: Provider `timeout_seconds`

**Files:**
- Modify: `backend/providers/base.py`
- Modify: `backend/providers/router.py`
- Modify: `config.yaml`
- Modify: `tests/test_providers.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_providers.py`:

```python
def test_provider_default_timeout():
    p = LMStudioProvider(base_url="http://localhost:1234/v1", model="qwen")
    assert p.timeout_seconds == 600

def test_router_reads_timeout_minutes_from_config():
    cfg = {
        "default_model": "lmstudio",
        "retry_policy": "auto",
        "providers": {
            "lmstudio": {
                "base_url": "http://localhost:1234/v1",
                "default_model": "qwen",
                "timeout_minutes": 5,
            }
        }
    }
    router = ProviderRouter(cfg)
    p = router.get_provider("lmstudio")
    assert p.timeout_seconds == 300

def test_router_default_timeout_when_absent():
    # _cfg has no timeout_minutes key
    router = ProviderRouter(_cfg)
    p = router.get_provider("lmstudio")
    assert p.timeout_seconds == 600
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_providers.py::test_provider_default_timeout tests/test_providers.py::test_router_reads_timeout_minutes_from_config tests/test_providers.py::test_router_default_timeout_when_absent -v
```

Expected: FAIL — `LLMProvider has no attribute timeout_seconds`

- [ ] **Step 3: Add `timeout_seconds` to base class**

In `backend/providers/base.py`, add the class attribute:

```python
class LLMProvider(ABC):
    is_local: bool = False
    concurrency: int = 1
    timeout_seconds: int = 600
    name: str

    @abstractmethod
    def get_llm(self) -> LLM:
        ...
```

- [ ] **Step 4: Set `timeout_seconds` from config in router**

In `backend/providers/router.py`, update `get_provider()` to set `timeout_seconds` after construction:

```python
def get_provider(self, name: str | None = None) -> LLMProvider:
    name = name or self.active_model
    cfg = self.config["providers"][name]
    concurrency = cfg.get("concurrency", 1)
    match name:
        case "openai":    provider = OpenAIProvider(api_key=cfg["api_key"], model=cfg["default_model"], concurrency=concurrency)
        case "anthropic": provider = AnthropicProvider(api_key=cfg["api_key"], model=cfg["default_model"], concurrency=concurrency)
        case "gemini":    provider = GeminiProvider(api_key=cfg["api_key"], model=cfg["default_model"], concurrency=concurrency)
        case "lmstudio":  provider = LMStudioProvider(base_url=cfg["base_url"], model=cfg["default_model"], concurrency=concurrency)
        case _: raise ValueError(f"Unknown provider: {name}")
    provider.timeout_seconds = cfg.get("timeout_minutes", 10) * 60
    return provider
```

- [ ] **Step 5: Add `timeout_minutes` to `config.yaml`**

```yaml
default_model: lmstudio
retry_policy: auto

providers:
  openai:
    api_key: ""
    default_model: gpt-4o-mini
    concurrency: 4
    timeout_minutes: 10
  anthropic:
    api_key: ""
    default_model: claude-sonnet-4-6
    concurrency: 4
    timeout_minutes: 10
  gemini:
    api_key: ""
    default_model: gemini-2.0-flash
    concurrency: 2
    timeout_minutes: 10
  lmstudio:
    base_url: http://localhost:1234/v1
    default_model: gemma-4-26b-a4b-it-uncensored
    concurrency: 4
    timeout_minutes: 10
```

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/test_providers.py -v
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add backend/providers/base.py backend/providers/router.py config.yaml tests/test_providers.py
git commit -m "feat: add timeout_seconds to LLMProvider, read from config timeout_minutes"
```

---

## Task 2: `WorkspaceManager.append_text()`

**Files:**
- Modify: `backend/workspace_manager.py`
- Create: `tests/test_workspace_append.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_workspace_append.py`:

```python
import pytest
from pathlib import Path
from backend.workspace_manager import WorkspaceManager


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.workspace_manager.WORKSPACE_ROOT", tmp_path)
    return WorkspaceManager("test-project")


def test_append_text_creates_file(ws):
    ws.append_text("_ors/run_log.txt", "first line\n")
    content = (ws.root / "_ors/run_log.txt").read_text(encoding="utf-8")
    assert content == "first line\n"


def test_append_text_accumulates(ws):
    ws.append_text("_ors/run_log.txt", "first\n")
    ws.append_text("_ors/run_log.txt", "second\n")
    content = (ws.root / "_ors/run_log.txt").read_text(encoding="utf-8")
    assert content == "first\nsecond\n"


def test_append_text_does_not_overwrite(ws):
    ws.write_text("_ors/run_log.txt", "existing\n")
    ws.append_text("_ors/run_log.txt", "new\n")
    content = (ws.root / "_ors/run_log.txt").read_text(encoding="utf-8")
    assert content == "existing\nnew\n"
```

- [ ] **Step 2: Run to verify failure**

```
pytest tests/test_workspace_append.py -v
```

Expected: FAIL — `WorkspaceManager has no attribute append_text`

- [ ] **Step 3: Implement `append_text()`**

In `backend/workspace_manager.py`, add after `write_text()`:

```python
def append_text(self, relative_path: str, content: str):
    target = self.root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        f.write(content)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_workspace_append.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/workspace_manager.py tests/test_workspace_append.py
git commit -m "feat: add WorkspaceManager.append_text for incremental log writes"
```

---

## Task 3: Startup Hook + Resume Endpoint

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/api/projects.py`
- Create: `tests/test_resume_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_resume_api.py`:

```python
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
    # Create a project stuck in "running" (simulates orphan from prior server crash)
    res = client.post("/projects", json={"spec": "Build a thing"})
    pid = res.json()["id"]
    db = next(client.app.dependency_overrides[get_db]())
    p = db.get(Project, pid)
    p.status = "running"
    db.commit()

    # Simulate lifespan startup by calling the reset function directly
    from backend.main import reset_orphaned_running_projects
    reset_orphaned_running_projects(db)
    db.refresh(p)
    assert p.status == "stalled"
```

- [ ] **Step 2: Run to verify failures**

```
pytest tests/test_resume_api.py -v
```

Expected: multiple FAILs — `reset_orphaned_running_projects` not found, resume endpoint doesn't exist

- [ ] **Step 3: Extract reset function and add to lifespan in `backend/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from backend.database import create_tables, SessionLocal
from backend.models import Project


def reset_orphaned_running_projects(db: Session):
    db.query(Project).filter(Project.status == "running").update({"status": "stalled"})
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    with SessionLocal() as db:
        reset_orphaned_running_projects(db)
    yield


app = FastAPI(title="ORS", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.api.stream import router as stream_router
from backend.api.projects import router as projects_router
from backend.api.settings import router as settings_router
app.include_router(stream_router)
app.include_router(projects_router)
app.include_router(settings_router)
```

- [ ] **Step 4: Add resume endpoint to `backend/api/projects.py`**

Add after the existing `delete_project` function:

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_resume_api.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/api/projects.py tests/test_resume_api.py
git commit -m "feat: add resume endpoint and startup hook for orphaned running projects"
```

---

## Task 4: Supervisor — Per-Worker Checkpoints + Log Writes

**Files:**
- Modify: `backend/orchestrator/supervisor.py`
- Create: `tests/test_supervisor_resume.py`

This task refactors `supervisor.py` to:
1. Extract `_run_generate()` from the inline generate block
2. Save `generate_worker_{i}` checkpoint per worker
3. On resume, skip workers that already have checkpoints
4. Write model output to `_ors/run_log.txt` after each step

- [ ] **Step 1: Write failing tests**

Create `tests/test_supervisor_resume.py`:

```python
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
         patch("backend.orchestrator.supervisor.make_file_writer"):
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
```

- [ ] **Step 2: Run to verify failures**

```
pytest tests/test_supervisor_resume.py -v
```

Expected: FAIL — `_run_generate` not defined, log files not created

- [ ] **Step 3: Refactor supervisor — extract `_run_generate()`, add per-worker checkpoints and log writes**

Replace `backend/orchestrator/supervisor.py` with:

```python
import asyncio
import json
import re
from datetime import datetime
from crewai import Crew, Process
from backend.models import Project
from backend.providers.router import ProviderRouter
from backend.orchestrator.checkpoint import CheckpointManager
from backend.orchestrator.crew import (
    build_clarify_task, build_architect_task, build_generate_task, build_generate_chunk_task,
    build_review_task, build_fix_task,
)
from backend.orchestrator.agents.clarifier import make_clarifier
from backend.orchestrator.agents.architect import make_architect
from backend.orchestrator.agents.file_writer import make_file_writer
from backend.orchestrator.agents.reviewer import make_reviewer
from backend.orchestrator.agents.fixer import make_fixer
from backend.workspace_manager import WorkspaceManager
from backend.event_bus import event_bus

MAX_FIX_ITERATIONS = 3


class Supervisor:
    def __init__(self, project_id: int, slug: str, spec: str,
                 router: ProviderRouter, checkpoint_mgr: CheckpointManager):
        self.project_id = project_id
        self.slug = slug
        self.spec = spec
        self.router = router
        self.ckpt = checkpoint_mgr
        self.ws = WorkspaceManager(slug)

    async def emit(self, task: str, event_type: str, data: dict | None = None):
        await event_bus.publish(self.project_id, {"task": task, "type": event_type, **(data or {})})

    def _llm(self):
        return self.router.get_provider().get_llm()

    def _set_status(self, status: str):
        p = self.ckpt.db.get(Project, self.project_id)
        if p:
            p.status = status
            self.ckpt.db.commit()

    def _ts(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    async def _run(self, task, agent) -> str:
        loop = asyncio.get_running_loop()
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
        result = await loop.run_in_executor(None, crew.kickoff)
        return result.raw

    def _write_files(self, raw: str):
        raw = raw.replace("\r\n", "\n")
        for m in re.finditer(r"=== FILE: (.+?) ===\s*\n([\s\S]*?)(?=\n=== FILE:|\Z)", raw):
            self.ws.write_file(m.group(1).strip(), m.group(2).strip())

    async def _run_worker(self, worker_id: int, files: list, spec: str, timeout_seconds: int) -> str:
        file_paths = [f["path"] for f in files]
        await self.emit("generate", "worker_started", {"worker_id": worker_id, "files": file_paths})
        agent = make_file_writer(self._llm())
        task = build_generate_chunk_task(agent, files, spec)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, crew.kickoff),
            timeout=timeout_seconds,
        )
        raw = result.raw
        self.ckpt.save(self.project_id, f"generate_worker_{worker_id}", self.router.active_model,
                       {"output": raw, "files": file_paths})
        entry = f"=== WORKER {worker_id} — {self._ts()} ===\nFiles: {', '.join(file_paths)}\n---\n{raw}\n\n"
        self.ws.append_text("_ors/generate_log.txt", entry)
        self.ws.append_text("_ors/run_log.txt", entry)
        await self.emit("generate", "worker_completed", {"worker_id": worker_id, "files": file_paths})
        return raw

    async def _run_generate(self, file_list: list, refined_spec: str) -> str:
        provider = self.router.get_provider()
        n = min(provider.concurrency, len(file_list))
        chunks = [file_list[i::n] for i in range(n)]

        results: dict[int, str] = {}
        pending: list[tuple[int, list]] = []

        for i, chunk in enumerate(chunks):
            cached = self.ckpt.load(self.project_id, f"generate_worker_{i}")
            if cached:
                results[i] = cached["output"]
                file_names = ", ".join(cached.get("files", []))
                skipped = f"=== WORKER {i} — skipped (checkpoint) ===\nFiles: {file_names}\n\n"
                self.ws.append_text("_ors/generate_log.txt", skipped)
                self.ws.append_text("_ors/run_log.txt", skipped)
            else:
                pending.append((i, chunk))

        if pending:
            new_results = await asyncio.gather(*[
                self._run_worker(i, chunk, refined_spec, provider.timeout_seconds)
                for i, chunk in pending
            ])
            for (i, _), result in zip(pending, new_results):
                results[i] = result

        return "\n".join(results[i] for i in sorted(results))

    async def run(self):
        # Clarify
        await self.emit("clarify", "started")
        cached = self.ckpt.load(self.project_id, "clarify")
        if cached:
            refined_spec = cached["refined_spec"]
        else:
            agent = make_clarifier(self._llm())
            refined_spec = await self._run(build_clarify_task(agent, self.spec), agent)
            self.ckpt.save(self.project_id, "clarify", self.router.active_model, {"refined_spec": refined_spec})
        self.ws.write_json("_ors/clarify.json", {"refined_spec": refined_spec})
        self.ws.append_text("_ors/run_log.txt", f"=== CLARIFY — {self._ts()} ===\n{refined_spec}\n\n")
        self.router.apply_pending()
        await self.emit("clarify", "completed", {"output": refined_spec})

        # Architect
        await self.emit("architect", "started")
        cached = self.ckpt.load(self.project_id, "architect")
        if cached:
            plan = cached["plan"]
        else:
            agent = make_architect(self._llm())
            plan = await self._run(build_architect_task(agent, refined_spec), agent)
            self.ckpt.save(self.project_id, "architect", self.router.active_model, {"plan": plan})
        self.ws.write_json("_ors/architect.json", {"plan": plan})
        self.ws.append_text("_ors/run_log.txt", f"=== ARCHITECT — {self._ts()} ===\n{plan}\n\n")
        self.router.apply_pending()
        await self.emit("architect", "completed", {"output": plan})

        # Generate
        await self.emit("generate", "started")
        cached = self.ckpt.load(self.project_id, "generate")
        if cached:
            files_content = cached["files_content"]
            self._write_files(files_content)
        else:
            try:
                plan_data = json.loads(plan)
                file_list = plan_data["files"]
            except (json.JSONDecodeError, KeyError, TypeError):
                file_list = None

            if file_list:
                files_content = await self._run_generate(file_list, refined_spec)
            else:
                agent = make_file_writer(self._llm())
                files_content = await self._run(build_generate_task(agent, plan, refined_spec), agent)

            self._write_files(files_content)
            self.ckpt.save(self.project_id, "generate", self.router.active_model, {"files_content": files_content})

        self.ws.write_text("_ors/generate.md", files_content)
        self.router.apply_pending()
        await self.emit("generate", "completed", {"file_tree": self.ws.file_tree()})

        # Review + Fix loop
        for i in range(MAX_FIX_ITERATIONS):
            await self.emit("review", "started", {"iteration": i + 1})
            reviewer = make_reviewer(self._llm())
            review = await self._run(build_review_task(reviewer, self.ws.file_tree(), files_content), reviewer)
            self.ws.write_json(f"_ors/review_{i + 1}.json", {"result": review})
            self.ws.append_text("_ors/run_log.txt", f"=== REVIEW {i + 1} — {self._ts()} ===\n{review}\n\n")

            if "PASS" in review:
                self.ckpt.save(self.project_id, "review", self.router.active_model, {"result": "PASS"})
                await self.emit("review", "completed", {"result": "PASS"})
                self.router.apply_pending()
                break

            if not self.router.should_auto_retry():
                self.router.apply_pending()
                self._set_status("paused")
                await self.emit("review", "paused", {"issues": review})
                return

            await self.emit("fix", "started", {"iteration": i + 1})
            fixer = make_fixer(self._llm())
            files_content = await self._run(build_fix_task(fixer, review, files_content), fixer)
            self._write_files(files_content)
            self.ws.write_text(f"_ors/fix_{i + 1}.md", files_content)
            self.ws.append_text("_ors/run_log.txt", f"=== FIX {i + 1} — {self._ts()} ===\n{files_content}\n\n")
            self.router.apply_pending()
            await self.emit("fix", "completed")
        else:
            await self.emit("review", "failed", {"message": f"Max fix iterations ({MAX_FIX_ITERATIONS}) reached without PASS"})

        self._set_status("done")
        await self.emit("done", "done", {"workspace": f"workspace/{self.slug}"})
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_supervisor_resume.py -v
```

Expected: all PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```
pytest -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/orchestrator/supervisor.py tests/test_supervisor_resume.py
git commit -m "feat: per-worker checkpoints, resume skip, and run_log writes in supervisor"
```

---

## Task 5: Supervisor — Timeout + Stalled Status

**Files:**
- Modify: `tests/test_supervisor_resume.py` (add timeout tests)
- No code change needed — timeout is already in `_run_worker` from Task 4. This task adds tests to verify it.

- [ ] **Step 1: Add timeout tests to `tests/test_supervisor_resume.py`**

Append to the file:

```python
@pytest.mark.asyncio
async def test_run_worker_raises_timeout(db, project, tmp_path):
    """Calls real _run_worker with a near-zero timeout — verifies asyncio.wait_for fires."""
    sup, ckpt = make_supervisor(db, project, tmp_path)

    import time

    def slow_kickoff():
        time.sleep(5)  # far longer than the 0.01s timeout

    with patch("backend.orchestrator.supervisor.Crew") as MockCrew, \
         patch("backend.orchestrator.supervisor.make_file_writer"):
        MockCrew.return_value.kickoff.side_effect = slow_kickoff
        with pytest.raises(asyncio.TimeoutError):
            await sup._run_worker(
                0, [{"path": "src/a.tsx", "description": "A"}], "spec", timeout_seconds=0.01
            )


@pytest.mark.asyncio
async def test_stalled_status_written_on_timeout(db, project, tmp_path):
    sup, ckpt = make_supervisor(db, project, tmp_path)

    # Pre-seed clarify and architect checkpoints so run() proceeds to generate
    ckpt.save(project.id, "clarify", "lmstudio", {"refined_spec": "spec"})
    ckpt.save(project.id, "architect", "lmstudio", {"plan": '{"files": [{"path": "src/a.tsx", "description": "A"}]}'})

    async def timeout_worker(worker_id, files, spec, timeout_seconds):
        raise asyncio.TimeoutError()

    with patch.object(sup, "_run_worker", side_effect=timeout_worker), \
         patch.object(sup, "emit", new=AsyncMock()):
        await sup.run()

    db.refresh(project)
    assert project.status == "stalled"
```

- [ ] **Step 2: The `run()` method needs to catch `TimeoutError` — update supervisor**

Add a `try/except` block around the generate call in `run()`. Find the generate section in `backend/orchestrator/supervisor.py` and wrap `_run_generate` and the fallback `_run`:

```python
        # Generate
        await self.emit("generate", "started")
        cached = self.ckpt.load(self.project_id, "generate")
        if cached:
            files_content = cached["files_content"]
            self._write_files(files_content)
        else:
            try:
                plan_data = json.loads(plan)
                file_list = plan_data["files"]
            except (json.JSONDecodeError, KeyError, TypeError):
                file_list = None

            try:
                if file_list:
                    files_content = await self._run_generate(file_list, refined_spec)
                else:
                    agent = make_file_writer(self._llm())
                    files_content = await self._run(build_generate_task(agent, plan, refined_spec), agent)
            except asyncio.TimeoutError:
                self._set_status("stalled")
                await self.emit("generate", "stalled", {"message": "LM Studio call timed out — resume when ready"})
                return

            self._write_files(files_content)
            self.ckpt.save(self.project_id, "generate", self.router.active_model, {"files_content": files_content})
```

- [ ] **Step 3: Run timeout tests**

```
pytest tests/test_supervisor_resume.py -v
```

Expected: all PASS

- [ ] **Step 4: Run full suite**

```
pytest -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/orchestrator/supervisor.py tests/test_supervisor_resume.py
git commit -m "feat: catch TimeoutError in generate, mark project stalled"
```

---

## Task 6: Frontend — API Client + Project Page

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/Project.tsx`

- [ ] **Step 1: Add `resumeProject` to `frontend/src/api/client.ts`**

Append to the file:

```typescript
export async function resumeProject(id: number): Promise<{ id: number; status: string }> {
  const res = await fetch(`${BASE}/projects/${id}/resume`, { method: "POST" });
  if (res.status === 409) {
    const data = await res.json();
    throw new Error(data.detail ?? "Cannot resume project");
  }
  if (!res.ok) throw new Error(`Resume failed: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Update `frontend/src/pages/Project.tsx`**

Make these four changes:

**a) Import `resumeProject`** — update the import line at the top:

```typescript
import { getProject, deleteProject, getLMStudioStatus, resumeProject } from "../api/client";
```

**b) Add `resuming` state** — add after the existing `useState` declarations:

```typescript
const [resuming, setResuming] = useState(false);
```

**c) Add `handleResume` function** — add after `handleDelete`:

```typescript
const handleResume = async () => {
  if (!project) return;
  setResuming(true);
  try {
    await resumeProject(project.id);
    setProject(p => p ? { ...p, status: "running" } : p);
  } finally {
    setResuming(false);
  }
};
```

**d) Replace the status badge span and add Resume button + log links** — replace:

```typescript
          <span
            className={`text-sm ${
              isDone
                ? "text-blue-400"
                : project.status === "failed"
                ? "text-red-400"
                : "text-green-400"
            }`}
          >
            {isDone ? "✓ Done" : project.status === "failed" ? "✗ Failed" : "● Running"}
          </span>
```

With:

```typescript
          {(project.status === "stalled" || project.status === "paused") && (
            <button
              onClick={handleResume}
              disabled={resuming}
              className="text-xs bg-orange-600 hover:bg-orange-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium px-2 py-1 rounded transition-colors"
            >
              {resuming ? "Resuming…" : "Resume"}
            </button>
          )}
          <span
            className={`text-sm ${
              isDone
                ? "text-blue-400"
                : project.status === "failed"
                ? "text-red-400"
                : project.status === "stalled"
                ? "text-orange-400"
                : project.status === "paused"
                ? "text-yellow-400"
                : "text-green-400"
            }`}
          >
            {isDone
              ? "✓ Done"
              : project.status === "failed"
              ? "✗ Failed"
              : project.status === "stalled"
              ? "⚠ Stalled"
              : project.status === "paused"
              ? "⏸ Paused"
              : "● Running"}
          </span>
```

**e) Replace the Done banner with one that also shows on stalled/failed and includes log links:**

Replace the entire `{isDone && (...)}` block at the bottom with:

```typescript
      {(isDone || project.status === "stalled" || project.status === "failed") && (
        <div className="px-6 pb-4 shrink-0">
          <div className={`border rounded-lg px-4 py-3 text-sm ${
            isDone
              ? "bg-green-950 border-green-700 text-green-300"
              : project.status === "stalled"
              ? "bg-orange-950 border-orange-700 text-orange-300"
              : "bg-red-950 border-red-700 text-red-300"
          }`}>
            {isDone
              ? <>✓ Build complete — files written to <code className="text-green-200">workspace/{project.slug}/</code></>
              : project.status === "stalled"
              ? "⚠ Run stalled (LM Studio timed out). Click Resume to continue from last checkpoint."
              : "✗ Run failed."}
            <span className="ml-4 space-x-3">
              <a
                href={`http://localhost:8000/workspace/${project.slug}/_ors/run_log.txt`}
                target="_blank"
                rel="noreferrer"
                className="underline opacity-70 hover:opacity-100"
              >
                View run log
              </a>
              <a
                href={`http://localhost:8000/workspace/${project.slug}/_ors/generate_log.txt`}
                target="_blank"
                rel="noreferrer"
                className="underline opacity-70 hover:opacity-100"
              >
                View generate log
              </a>
            </span>
          </div>
        </div>
      )}
```

- [ ] **Step 3: Start the dev server and verify manually**

```
cd frontend && npm run dev
```

Check:
- A stalled project shows "⚠ Stalled" orange badge and "Resume" button
- A paused project shows "⏸ Paused" yellow badge and "Resume" button
- Clicking Resume calls the API and badge switches to "● Running"
- Done banner and stalled banner both show log links

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/Project.tsx
git commit -m "feat: resume button, stalled/paused badge, and log links in Project page"
```

---

## Task 7: Frontend — Gallery Status Colors + Polling

**Files:**
- Modify: `frontend/src/pages/Gallery.tsx`

- [ ] **Step 1: Update `STATUS_COLOR` and polling in `Gallery.tsx`**

**a) Update `STATUS_COLOR`** — replace the existing map:

```typescript
const STATUS_COLOR: Record<string, string> = {
  running: "text-green-400",
  done: "text-blue-400",
  failed: "text-red-400",
  stalled: "text-orange-400",
  paused: "text-yellow-400",
  pending: "text-gray-400",
};
```

**b) Update polling** — also poll when there are stalled/paused projects (so status updates after resume). Replace the polling `useEffect`:

```typescript
  useEffect(() => {
    const hasActive = projects.some(p => p.status === "running" || p.status === "stalled" || p.status === "paused");
    if (!hasActive) return;
    const id = setInterval(fetchProjects, 10_000);
    return () => clearInterval(id);
  }, [projects]);
```

- [ ] **Step 2: Check gallery in browser**

Navigate to `/` — stalled projects should show orange text, paused projects yellow text.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Gallery.tsx
git commit -m "feat: stalled/paused status colors in Gallery"
```

---

## Task 8: End-to-End Smoke Check + Final Commit

- [ ] **Step 1: Run full test suite one final time**

```
pytest -v
```

Expected: all PASS

- [ ] **Step 2: Push to GitHub**

```bash
git push origin master
```

- [ ] **Step 3: Manual smoke test checklist**

- [ ] Start backend: `uvicorn backend.main:app --reload`
- [ ] Start frontend: `cd frontend && npm run dev`
- [ ] Create a new project — verify it starts and runs normally (no regression)
- [ ] In `config.yaml`, set `timeout_minutes: 0` temporarily, create a project — verify it stalls immediately and shows "⚠ Stalled" badge
- [ ] Click Resume — verify it re-runs the supervisor and skips completed checkpoints
- [ ] Verify `workspace/<slug>/_ors/run_log.txt` exists and contains model output
- [ ] Restore `timeout_minutes: 10` in `config.yaml`
