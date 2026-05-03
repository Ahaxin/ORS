# ORS Feature Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add delete project, per-step output files, LM Studio model status, parallel file generation, and gallery auto-refresh to the ORS FastAPI + React app.

**Architecture:** Backend tasks (1–6) are independent of each other except Task 5 depends on Task 1, and Task 6 depends on Task 2. Frontend tasks (7–11) all depend on the backend being done first. Each task produces a passing test suite before the next begins.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy/SQLite, CrewAI, httpx, pytest; React 18, TypeScript, Tailwind CSS, Vite

---

## File Map

| File | Tasks |
|------|-------|
| `backend/workspace_manager.py` | Task 1 |
| `backend/providers/base.py` | Task 2 |
| `backend/providers/openai_provider.py` | Task 2 |
| `backend/providers/anthropic_provider.py` | Task 2 |
| `backend/providers/gemini_provider.py` | Task 2 |
| `backend/providers/lmstudio_provider.py` | Task 2 |
| `backend/providers/router.py` | Task 2 |
| `config.yaml` | Task 2 |
| `backend/api/projects.py` | Task 3 |
| `backend/api/settings.py` | Task 4 |
| `backend/orchestrator/supervisor.py` | Tasks 5, 6 |
| `backend/orchestrator/crew.py` | Task 6 |
| `tests/test_models.py` | Task 1 |
| `tests/test_providers.py` | Task 2 |
| `tests/test_projects_api.py` | Task 3 |
| `tests/test_lmstudio_status.py` | Task 4 (new file) |
| `tests/test_crew.py` | Task 6 (new file) |
| `frontend/src/api/client.ts` | Task 7 |
| `frontend/src/hooks/useSSE.ts` | Task 8 |
| `frontend/src/components/TaskBoard.tsx` | Task 9 |
| `frontend/src/pages/Gallery.tsx` | Task 10 |
| `frontend/src/pages/Project.tsx` | Task 11 |

---

## Task 1: WorkspaceManager helpers

**Files:**
- Modify: `backend/workspace_manager.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_models.py`:

```python
import json

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
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/test_models.py::test_write_json tests/test_models.py::test_write_text -v
```
Expected: `AttributeError: 'WorkspaceManager' object has no attribute 'write_json'`

- [ ] **Step 3: Implement helpers in `backend/workspace_manager.py`**

Add after the existing `write_file` method:

```python
def write_json(self, relative_path: str, data: dict):
    import json
    self.write_file(relative_path, json.dumps(data, indent=2))

def write_text(self, relative_path: str, content: str):
    self.write_file(relative_path, content)
```

- [ ] **Step 4: Run tests — verify they pass**

```
pytest tests/test_models.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```
git add backend/workspace_manager.py tests/test_models.py
git commit -m "feat: add write_json and write_text helpers to WorkspaceManager"
```

---

## Task 2: Provider concurrency

**Files:**
- Modify: `backend/providers/base.py`
- Modify: `backend/providers/openai_provider.py`
- Modify: `backend/providers/anthropic_provider.py`
- Modify: `backend/providers/gemini_provider.py`
- Modify: `backend/providers/lmstudio_provider.py`
- Modify: `backend/providers/router.py`
- Modify: `config.yaml`
- Modify: `tests/test_providers.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_providers.py`:

```python
def test_provider_default_concurrency():
    p = LMStudioProvider(base_url="http://localhost:1234/v1", model="qwen")
    assert p.concurrency == 1

def test_provider_custom_concurrency():
    p = OpenAIProvider(api_key="sk-test", model="gpt-4o-mini", concurrency=4)
    assert p.concurrency == 4

def test_router_passes_concurrency():
    cfg = {
        **_cfg,
        "providers": {
            **_cfg["providers"],
            "openai": {"api_key": "sk-test", "default_model": "gpt-4o-mini", "concurrency": 4},
        }
    }
    router = ProviderRouter(cfg)
    assert router.get_provider("openai").concurrency == 4

def test_router_default_concurrency_when_absent():
    router = ProviderRouter(_cfg)  # _cfg has no concurrency keys
    assert router.get_provider("lmstudio").concurrency == 1
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/test_providers.py::test_provider_default_concurrency tests/test_providers.py::test_provider_custom_concurrency -v
```
Expected: `AttributeError: 'LMStudioProvider' object has no attribute 'concurrency'`

- [ ] **Step 3: Add `concurrency` to base class**

In `backend/providers/base.py`, add `concurrency: int = 1` as a class attribute:

```python
from abc import ABC, abstractmethod
from crewai import LLM


class LLMProvider(ABC):
    is_local: bool = False
    concurrency: int = 1

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def get_llm(self) -> LLM:
        ...
```

- [ ] **Step 4: Update each provider constructor**

`backend/providers/lmstudio_provider.py`:
```python
from crewai import LLM
from backend.providers.base import LLMProvider


class LMStudioProvider(LLMProvider):
    name = "lmstudio"
    is_local = True

    def __init__(self, base_url: str, model: str, concurrency: int = 1):
        self.base_url = base_url
        self.model = model
        self.concurrency = concurrency

    def get_llm(self):
        return LLM(model=f"openai/{self.model}", base_url=self.base_url, api_key="lm-studio")
```

`backend/providers/openai_provider.py`:
```python
from crewai import LLM
from backend.providers.base import LLMProvider

class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", concurrency: int = 1):
        self.api_key = api_key
        self.model = model
        self.concurrency = concurrency

    def get_llm(self) -> LLM:
        return LLM(model=self.model, api_key=self.api_key)
```

`backend/providers/anthropic_provider.py`:
```python
from crewai import LLM
from backend.providers.base import LLMProvider

class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6", concurrency: int = 1):
        self.api_key = api_key
        self.model = model
        self.concurrency = concurrency

    def get_llm(self) -> LLM:
        return LLM(model=f"anthropic/{self.model}", api_key=self.api_key)
```

`backend/providers/gemini_provider.py`:
```python
from crewai import LLM
from backend.providers.base import LLMProvider

class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash", concurrency: int = 1):
        self.api_key = api_key
        self.model = model
        self.concurrency = concurrency

    def get_llm(self) -> LLM:
        return LLM(model=f"gemini/{self.model}", api_key=self.api_key)
```

- [ ] **Step 5: Update `ProviderRouter.get_provider()` to pass concurrency**

Replace the `match` block in `backend/providers/router.py`:

```python
def get_provider(self, name: str | None = None) -> LLMProvider:
    name = name or self.active_model
    cfg = self.config["providers"][name]
    concurrency = cfg.get("concurrency", 1)
    match name:
        case "openai":
            return OpenAIProvider(api_key=cfg["api_key"], model=cfg["default_model"], concurrency=concurrency)
        case "anthropic":
            return AnthropicProvider(api_key=cfg["api_key"], model=cfg["default_model"], concurrency=concurrency)
        case "gemini":
            return GeminiProvider(api_key=cfg["api_key"], model=cfg["default_model"], concurrency=concurrency)
        case "lmstudio":
            return LMStudioProvider(base_url=cfg["base_url"], model=cfg["default_model"], concurrency=concurrency)
        case _:
            raise ValueError(f"Unknown provider: {name}")
```

- [ ] **Step 6: Add `concurrency` keys to `config.yaml`**

```yaml
default_model: lmstudio
retry_policy: auto

providers:
  openai:
    api_key: ""
    default_model: gpt-4o-mini
    concurrency: 4
  anthropic:
    api_key: ""
    default_model: claude-sonnet-4-6
    concurrency: 4
  gemini:
    api_key: ""
    default_model: gemini-2.0-flash
    concurrency: 2
  lmstudio:
    base_url: http://localhost:1234/v1
    default_model: gemma-4-26b-a4b-it-uncensored
    concurrency: 4
```

- [ ] **Step 7: Run all provider tests — verify they pass**

```
pytest tests/test_providers.py -v
```
Expected: all pass (including pre-existing tests — `concurrency=1` default keeps them valid)

- [ ] **Step 8: Commit**

```
git add backend/providers/ config.yaml tests/test_providers.py
git commit -m "feat: add concurrency to provider base class, constructors, router, and config"
```

---

## Task 3: Delete project endpoint

**Files:**
- Modify: `backend/api/projects.py`
- Modify: `tests/test_projects_api.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_projects_api.py`:

```python
def test_delete_project(client):
    res = client.post("/projects", json={"spec": "Build a blog"})
    pid = res.json()["id"]
    res = client.delete(f"/projects/{pid}")
    assert res.status_code == 204

def test_delete_project_not_found(client):
    res = client.delete("/projects/9999")
    assert res.status_code == 404

def test_delete_running_project_returns_409(client):
    res = client.post("/projects", json={"spec": "Build a blog"})
    pid = res.json()["id"]
    # Set status to "running" via the model endpoint — the fixture mocks _run so it never flips to done.
    # We reach into the DB session via the override generator using next().
    from backend.database import get_db
    from backend.models import Project
    db = next(client.app.dependency_overrides[get_db]())
    p = db.get(Project, pid)
    p.status = "running"
    db.commit()
    res = client.delete(f"/projects/{pid}")
    assert res.status_code == 409

def test_delete_removes_from_list(client):
    res = client.post("/projects", json={"spec": "Build a shop"})
    pid = res.json()["id"]
    client.delete(f"/projects/{pid}")
    projects = client.get("/projects").json()
    assert not any(p["id"] == pid for p in projects)
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/test_projects_api.py::test_delete_project tests/test_projects_api.py::test_delete_project_not_found -v
```
Expected: `405 Method Not Allowed` (route not defined yet)

- [ ] **Step 3: Implement the DELETE endpoint**

Add `import shutil` at the top of `backend/api/projects.py` (no need to import `Path` — use `WorkspaceManager.root` which already resolves via `WORKSPACE_ROOT`). Also add `from backend.workspace_manager import WorkspaceManager` to the imports.

Add the endpoint after `get_project`:

```python
@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    if p.status == "running":
        raise HTTPException(status_code=409, detail="Cannot delete a running project")
    slug = p.slug
    db.delete(p)
    db.commit()
    workspace_root = WorkspaceManager(slug).root
    if workspace_root.exists():
        shutil.rmtree(workspace_root)
```

Full imports block at top of `backend/api/projects.py`:
```python
import re
import shutil
import time
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Project
from backend.providers.router import ProviderRouter
from backend.orchestrator.checkpoint import CheckpointManager
from backend.orchestrator.supervisor import Supervisor
from backend.workspace_manager import WorkspaceManager
from pydantic import BaseModel
```

- [ ] **Step 4: Run tests — verify they pass**

```
pytest tests/test_projects_api.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```
git add backend/api/projects.py tests/test_projects_api.py
git commit -m "feat: add DELETE /projects/{id} with 409 guard for running projects"
```

---

## Task 4: LM Studio status endpoint

**Files:**
- Modify: `backend/api/settings.py`
- Create: `tests/test_lmstudio_status.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lmstudio_status.py`:

```python
import pytest
from unittest import mock
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

_fake_config = {
    "default_model": "lmstudio",
    "retry_policy": "auto",
    "providers": {
        "lmstudio": {
            "base_url": "http://localhost:1234/v1",
            "default_model": "qwen2.5-coder",
            "concurrency": 4,
        },
        "openai": {"api_key": "", "default_model": "gpt-4o-mini", "concurrency": 4},
        "anthropic": {"api_key": "", "default_model": "claude-sonnet-4-6", "concurrency": 4},
        "gemini": {"api_key": "", "default_model": "gemini-2.0-flash", "concurrency": 2},
    },
}


def _mock_router():
    from backend.providers.router import ProviderRouter
    return ProviderRouter(_fake_config)


def test_lmstudio_status_ready():
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {"object": "list", "data": [{"id": "qwen2.5-coder"}]}
    mock_response.raise_for_status = mock.MagicMock()

    with mock.patch("backend.api.settings.ProviderRouter.from_config_file", return_value=_mock_router()), \
         mock.patch("httpx.get", return_value=mock_response):
        res = client.get("/providers/lmstudio/status")

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["model"] == "qwen2.5-coder"


def test_lmstudio_status_unavailable_empty_list():
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {"object": "list", "data": []}
    mock_response.raise_for_status = mock.MagicMock()

    with mock.patch("backend.api.settings.ProviderRouter.from_config_file", return_value=_mock_router()), \
         mock.patch("httpx.get", return_value=mock_response):
        res = client.get("/providers/lmstudio/status")

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "unavailable"
    assert data["model"] is None


def test_lmstudio_status_unavailable_on_connection_error():
    with mock.patch("backend.api.settings.ProviderRouter.from_config_file", return_value=_mock_router()), \
         mock.patch("httpx.get", side_effect=Exception("connection refused")):
        res = client.get("/providers/lmstudio/status")

    assert res.status_code == 200
    assert res.json()["status"] == "unavailable"
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/test_lmstudio_status.py -v
```
Expected: `404 Not Found` (route not yet defined)

- [ ] **Step 3: Implement the endpoint in `backend/api/settings.py`**

```python
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
    except Exception:
        return {"model": None, "status": "unavailable"}
```

- [ ] **Step 4: Run tests — verify they pass**

```
pytest tests/test_lmstudio_status.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```
git add backend/api/settings.py tests/test_lmstudio_status.py
git commit -m "feat: add GET /providers/lmstudio/status endpoint"
```

---

## Task 5: Per-step output files in Supervisor

**Files:**
- Modify: `backend/orchestrator/supervisor.py`

This task has no isolated unit test (the Supervisor integrates CrewAI which can't be unit-tested without a live LLM). Correctness is verified by running the app and checking `workspace/<slug>/_ors/` after a pipeline run.

- [ ] **Step 1: Add `_ors/` writes after each `ckpt.save()` call in `supervisor.py`**

In `supervisor.py`, update the `run` method. After the existing `self.ckpt.save(...)` and cache-hit blocks, add the workspace write. The pattern is the same for every step — write immediately after saving (or loading from cache):

**Clarify block** — add after the `if/else`:
```python
        self.ckpt.save(self.project_id, "clarify", self.router.active_model, {"refined_spec": refined_spec})
        self.ws.write_json("_ors/clarify.json", {"refined_spec": refined_spec})
```
Cache hit: add `self.ws.write_json("_ors/clarify.json", {"refined_spec": refined_spec})` after `refined_spec = cached["refined_spec"]`.

**Architect block** — same pattern:
```python
        self.ckpt.save(self.project_id, "architect", self.router.active_model, {"plan": plan})
        self.ws.write_json("_ors/architect.json", {"plan": plan})
```
Cache hit: `self.ws.write_json("_ors/architect.json", {"plan": plan})` after `plan = cached["plan"]`.

**Generate block** — write merged output:
```python
        self.ckpt.save(self.project_id, "generate", self.router.active_model, {"files_content": files_content})
        self.ws.write_text("_ors/generate.md", files_content)
```
Cache hit: `self.ws.write_text("_ors/generate.md", files_content)` after `files_content = cached["files_content"]`.

**Review block** (inside loop) — write **unconditionally** for both PASS and issues outcomes:
```python
        review = await self._run(build_review_task(reviewer, self.ws.file_tree(), files_content), reviewer)
        self.ws.write_json("_ors/review.json", {"result": review})  # write before branching

        if "PASS" in review:
            ...
```
This must come immediately after `review = await self._run(...)` and before any `if "PASS"` check, so both the pass and issues paths produce a file.

**Fix block** (inside loop, iteration i is 0-based):
```python
        self.ws.write_text(f"_ors/fix_{i + 1}.md", files_content)
```
Write this after `files_content = await self._run(build_fix_task(...), fixer)`.

- [ ] **Step 2: Verify manually**

Run the backend (`uvicorn backend.main:app --reload`), create a project, and after any step completes check:
```
workspace/<slug>/_ors/clarify.json   ← exists and contains {"refined_spec": "..."}
workspace/<slug>/_ors/architect.json ← exists after architect step
workspace/<slug>/_ors/generate.md    ← exists after generate step
```

- [ ] **Step 3: Commit**

```
git add backend/orchestrator/supervisor.py
git commit -m "feat: write per-step outputs to workspace/_ors/ after each pipeline step"
```

---

## Task 6: Parallel generate step

**Files:**
- Modify: `backend/orchestrator/crew.py`
- Modify: `backend/orchestrator/supervisor.py`
- Create: `tests/test_crew.py`

- [ ] **Step 1: Write failing test for `build_generate_chunk_task`**

Create `tests/test_crew.py`:

```python
from backend.orchestrator.crew import build_generate_chunk_task
from unittest import mock


def _fake_agent():
    return mock.MagicMock()


def test_chunk_task_description_contains_file_paths():
    files = [
        {"path": "src/app.ts", "description": "main entry"},
        {"path": "src/index.ts", "description": "index"},
    ]
    task = build_generate_chunk_task(_fake_agent(), files, "Build a todo app")
    assert "src/app.ts" in task.description
    assert "src/index.ts" in task.description
    assert "Build a todo app" in task.description


def test_chunk_task_description_forbids_placeholders():
    files = [{"path": "src/app.ts", "description": "entry"}]
    task = build_generate_chunk_task(_fake_agent(), files, "spec")
    assert "<path>" not in task.description
    assert "<content>" not in task.description


def test_chunk_task_expected_output_mentions_headers():
    files = [{"path": "src/app.ts", "description": "entry"}]
    task = build_generate_chunk_task(_fake_agent(), files, "spec")
    assert "===" in task.expected_output
```

- [ ] **Step 2: Run tests — verify they fail**

```
pytest tests/test_crew.py -v
```
Expected: `ImportError: cannot import name 'build_generate_chunk_task'`

- [ ] **Step 3: Add `build_generate_chunk_task` to `backend/orchestrator/crew.py`**

Add after the existing `build_generate_task` function:

```python
def build_generate_chunk_task(agent, files: list[dict], spec: str) -> Task:
    file_list = "\n".join(f"- {f['path']}: {f['description']}" for f in files)
    return Task(
        description=(
            f"Generate ONLY these files:\n{file_list}\n\nSpec: {spec}\n\n"
            "Output each file using this EXACT format:\n\n"
            "=== FILE: src/index.ts ===\n"
            "// content here\n\n"
            "=== FILE: src/app.ts ===\n"
            "// content here\n\n"
            "Do not use placeholder text like <path> or <content>."
        ),
        expected_output="All assigned files with === FILE: <actual path> === headers and full content. No placeholders.",
        agent=agent,
    )
```

- [ ] **Step 4: Run crew tests — verify they pass**

```
pytest tests/test_crew.py -v
```
Expected: all pass

- [ ] **Step 5: Update `supervisor.py` — add `_run_worker` and parallel generate**

Add `import json` at the top of `supervisor.py` (after existing imports).

Add `build_generate_chunk_task` to the import from `backend.orchestrator.crew`.

Add the `_run_worker` method to the `Supervisor` class (after `_write_files`):

```python
async def _run_worker(self, worker_id: int, files: list, spec: str) -> str:
    await self.emit("generate", "worker_started", {
        "worker_id": worker_id,
        "files": [f["path"] for f in files],
    })
    agent = make_file_writer(self._llm())
    task = build_generate_chunk_task(agent, files, spec)
    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, crew.kickoff)
    await self.emit("generate", "worker_completed", {
        "worker_id": worker_id,
        "files": [f["path"] for f in files],
    })
    return result.raw
```

Replace the generate step's `else` branch in `run()` (the non-cache path) with:

```python
        else:
            try:
                plan_data = json.loads(plan)
                file_list = plan_data["files"]
            except (json.JSONDecodeError, KeyError, TypeError):
                file_list = None

            if file_list:
                concurrency = self.router.get_provider().concurrency
                n = min(concurrency, len(file_list))
                chunks = [file_list[i::n] for i in range(n)]
                results = await asyncio.gather(*[
                    self._run_worker(i, chunk, refined_spec)
                    for i, chunk in enumerate(chunks)
                ])
                files_content = "\n".join(results)
            else:
                agent = make_file_writer(self._llm())
                files_content = await self._run(build_generate_task(agent, plan, refined_spec), agent)

            self._write_files(files_content)
            self.ckpt.save(self.project_id, "generate", self.router.active_model, {"files_content": files_content})
            self.ws.write_text("_ors/generate.md", files_content)
```

- [ ] **Step 6: Run full test suite — verify no regressions**

```
pytest tests/ -v
```
Expected: all pass

- [ ] **Step 7: Commit**

```
git add backend/orchestrator/crew.py backend/orchestrator/supervisor.py tests/test_crew.py
git commit -m "feat: parallel file generation with worker SSE events and JSON plan fallback"
```

---

## Task 7: Frontend API client additions

**Files:**
- Modify: `frontend/src/api/client.ts`

No automated test setup exists for the frontend. Type-check with `npm run build` as verification.

- [ ] **Step 1: Add `deleteProject` and `getLMStudioStatus` to `client.ts`**

```typescript
const BASE = "http://localhost:8000";

export async function createProject(spec: string, model?: string) {
  const res = await fetch(`${BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ spec, model }),
  });
  return res.json();
}

export const listProjects = () => fetch(`${BASE}/projects`).then(r => r.json());

export const getProject = (id: number) => fetch(`${BASE}/projects/${id}`).then(r => r.json());

export async function switchModel(projectId: number, model: string) {
  return fetch(`${BASE}/projects/${projectId}/model`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  }).then(r => r.json());
}

export async function deleteProject(id: number): Promise<void> {
  const res = await fetch(`${BASE}/projects/${id}`, { method: "DELETE" });
  if (res.status === 409) throw new Error("Cannot delete a running project");
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}

export async function getLMStudioStatus(): Promise<{ model: string | null; status: string }> {
  return fetch(`${BASE}/providers/lmstudio/status`).then(r => r.json());
}
```

- [ ] **Step 2: Verify type-check passes**

```
cd frontend && npm run build
```
Expected: no TypeScript errors in `client.ts`

- [ ] **Step 3: Commit**

```
git add frontend/src/api/client.ts
git commit -m "feat: add deleteProject and getLMStudioStatus to API client"
```

---

## Task 8: useSSE discriminated union

**Files:**
- Modify: `frontend/src/hooks/useSSE.ts`

- [ ] **Step 1: Replace the `TaskEvent` type with the discriminated union**

```typescript
import { useEffect, useState } from "react";

export type StepEvent = {
  task: string;
  type: "started" | "completed" | "paused" | "failed" | "done";
  output?: string;
  issues?: string;
  file_tree?: string;
  iteration?: number;
  result?: string;
  workspace?: string;
  message?: string;
};

export type WorkerEvent = {
  task: "generate";
  type: "worker_started" | "worker_completed";
  worker_id: number;
  files: string[];
};

export type TaskEvent = StepEvent | WorkerEvent;

export function useSSE(projectId: number | null) {
  const [events, setEvents] = useState<TaskEvent[]>([]);

  useEffect(() => {
    if (!projectId) return;
    const es = new EventSource(`http://localhost:8000/projects/${projectId}/stream`);
    es.onmessage = (e) => setEvents(prev => [...prev, JSON.parse(e.data) as TaskEvent]);
    es.onerror = () => es.close();
    return () => es.close();
  }, [projectId]);

  return events;
}
```

- [ ] **Step 2: Verify build passes**

```
cd frontend && npm run build
```
Expected: no TypeScript errors. Any component importing `TaskEvent` may now need to handle the union — fix any resulting type errors (likely in `TaskBoard.tsx`, addressed in Task 9).

- [ ] **Step 3: Commit**

```
git add frontend/src/hooks/useSSE.ts
git commit -m "feat: extend TaskEvent to discriminated union with WorkerEvent for parallel generate"
```

---

## Task 9: TaskBoard worker sub-rows

**Files:**
- Modify: `frontend/src/components/TaskBoard.tsx`

- [ ] **Step 1: Update `TaskBoard` to filter step events and render worker sub-rows**

```typescript
import type { TaskEvent, StepEvent, WorkerEvent } from "../hooks/useSSE";

const TASKS = ["clarify", "architect", "generate", "review", "fix"];

type Props = { events: TaskEvent[]; activeModel: string; pendingModel?: string };

const isStepEvent = (e: TaskEvent): e is StepEvent =>
  e.type !== "worker_started" && e.type !== "worker_completed";

const isWorkerEvent = (e: TaskEvent): e is WorkerEvent =>
  e.type === "worker_started" || e.type === "worker_completed";

export default function TaskBoard({ events, activeModel, pendingModel }: Props) {
  const stepEvents = events.filter(isStepEvent);
  const workerEvents = events.filter(isWorkerEvent);

  const statusOf = (task: string) => {
    const last = [...stepEvents].reverse().find(e => e.task === task);
    if (!last) return "pending";
    if (last.type === "completed" || last.type === "done") return "done";
    if (last.type === "paused") return "paused";
    if (last.type === "failed") return "failed";
    return "running";
  };

  const colors: Record<string, string> = {
    done: "text-green-400 border-green-800 bg-green-950",
    running: "text-yellow-300 border-blue-700 bg-blue-950",
    paused: "text-orange-400 border-orange-700 bg-orange-950",
    failed: "text-red-400 border-red-800 bg-red-950",
    pending: "text-gray-600 border-gray-800 bg-gray-950",
  };

  // Build worker status map: { workerId -> "running" | "done" }
  const workerStatus = new Map<number, "running" | "done">();
  for (const e of workerEvents) {
    workerStatus.set(e.worker_id, e.type === "worker_completed" ? "done" : "running");
  }
  const workerFileMap = new Map<number, string[]>();
  for (const e of workerEvents) {
    if (!workerFileMap.has(e.worker_id)) workerFileMap.set(e.worker_id, e.files);
  }

  const generateStatus = statusOf("generate");
  const allWorkersDone = workerStatus.size > 0 && [...workerStatus.values()].every(s => s === "done");
  const showWorkers = generateStatus === "running" || (workerStatus.size > 0 && !allWorkersDone);

  return (
    <div className="flex flex-col gap-2 w-64 shrink-0">
      {TASKS.map(task => {
        const status = statusOf(task);
        return (
          <div key={task}>
            <div className={`border rounded-lg p-3 ${colors[status]}`}>
              <div className="font-medium capitalize">{task}</div>
              <div className="text-xs opacity-60">
                {activeModel}{status === "running" ? " · running…" : ""}
              </div>
            </div>
            {task === "generate" && showWorkers && (
              <div className="ml-3 mt-1 flex flex-col gap-1">
                {[...workerFileMap.entries()].map(([id, files]) => {
                  const ws = workerStatus.get(id) ?? "running";
                  return (
                    <div key={id} className={`text-xs px-2 py-1 rounded border ${
                      ws === "done"
                        ? "border-green-900 bg-green-950 text-green-400"
                        : "border-blue-900 bg-blue-950 text-blue-300"
                    }`}>
                      <span className="font-medium">Worker {id + 1}:</span>{" "}
                      {files.slice(0, 3).join(", ")}{files.length > 3 ? ` +${files.length - 3}` : ""}{" "}
                      <span className="opacity-60">{ws === "done" ? "● done" : "● running"}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
      {pendingModel && (
        <div className="text-xs text-yellow-400 mt-1">⚑ Switching to {pendingModel} at next task</div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify build passes**

```
cd frontend && npm run build
```
Expected: no TypeScript errors

- [ ] **Step 3: Commit**

```
git add frontend/src/components/TaskBoard.tsx
git commit -m "feat: TaskBoard worker sub-rows for parallel generate step"
```

---

## Task 10: Gallery delete button and polling refresh

**Files:**
- Modify: `frontend/src/pages/Gallery.tsx`

- [ ] **Step 1: Rewrite `Gallery.tsx` with delete confirmation and polling**

```typescript
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { listProjects, deleteProject } from "../api/client";

type ProjectSummary = {
  id: number;
  slug: string;
  status: string;
  active_model: string;
};

const STATUS_COLOR: Record<string, string> = {
  running: "text-green-400",
  done: "text-blue-400",
  failed: "text-red-400",
  pending: "text-gray-400",
};

export default function Gallery() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<Record<number, string>>({});
  const fetchingRef = useRef(false);

  const fetchProjects = async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      const data = await listProjects();
      setProjects(data);
    } catch (e) {
      console.error("Failed to fetch projects", e);
    } finally {
      fetchingRef.current = false;
    }
  };

  useEffect(() => {
    fetchProjects().finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const hasRunning = projects.some(p => p.status === "running");
    if (!hasRunning) return;
    const id = setInterval(fetchProjects, 10_000);
    return () => clearInterval(id);
  }, [projects]);

  const handleDelete = async (id: number) => {
    try {
      await deleteProject(id);
      setProjects(prev => prev.filter(p => p.id !== id));
      setConfirmId(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Delete failed";
      setDeleteError(prev => ({ ...prev, [id]: msg }));
      setConfirmId(null);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-2xl font-bold text-yellow-400">⚡ ORS</h1>
          <Link
            to="/new"
            className="bg-yellow-500 text-black font-bold px-4 py-2 rounded-lg hover:bg-yellow-400 transition-colors"
          >
            + New Project
          </Link>
        </div>

        {loading ? (
          <p className="text-gray-500">Loading…</p>
        ) : projects.length === 0 ? (
          <div className="text-center py-24 space-y-3">
            <p className="text-gray-500 text-lg">No projects yet.</p>
            <Link to="/new" className="text-yellow-400 hover:text-yellow-300 transition-colors">
              Build your first app →
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((p) => (
              <div key={p.id} className="relative group">
                <Link
                  to={`/projects/${p.id}`}
                  className="block bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-gray-600 transition-colors"
                >
                  <div className="font-medium text-gray-100 group-hover:text-white transition-colors truncate pr-6">
                    {p.slug}
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <span className={`text-xs ${STATUS_COLOR[p.status] ?? "text-gray-400"}`}>
                      {p.status}
                    </span>
                    <span className="text-gray-700">·</span>
                    <span className="text-xs text-gray-500">{p.active_model}</span>
                  </div>
                  {deleteError[p.id] && (
                    <p className="text-xs text-red-400 mt-1">{deleteError[p.id]}</p>
                  )}
                </Link>

                {/* Delete button — visible on hover, disabled for running projects */}
                {confirmId === p.id ? (
                  <div className="absolute top-2 right-2 flex items-center gap-1 bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-xs z-10">
                    <span className="text-gray-300">Delete?</span>
                    <button
                      onClick={(e) => { e.preventDefault(); handleDelete(p.id); }}
                      className="text-red-400 hover:text-red-300 font-medium"
                    >Yes</button>
                    <button
                      onClick={(e) => { e.preventDefault(); setConfirmId(null); }}
                      className="text-gray-400 hover:text-gray-200"
                    >No</button>
                  </div>
                ) : (
                  <button
                    onClick={(e) => { e.preventDefault(); setConfirmId(p.id); }}
                    disabled={p.status === "running"}
                    className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 disabled:opacity-20 disabled:cursor-not-allowed transition-opacity text-sm font-bold"
                    title={p.status === "running" ? "Can't delete a running project" : "Delete project"}
                  >×</button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build passes**

```
cd frontend && npm run build
```
Expected: no TypeScript errors

- [ ] **Step 3: Commit**

```
git add frontend/src/pages/Gallery.tsx
git commit -m "feat: Gallery delete button with inline confirmation and 10s polling for running projects"
```

---

## Task 11: Project page delete button and LM Studio badge

**Files:**
- Modify: `frontend/src/pages/Project.tsx`

- [ ] **Step 1: Rewrite `Project.tsx` with delete button and LM Studio status badge**

```typescript
import { useParams, Link, useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { getProject, deleteProject, getLMStudioStatus } from "../api/client";
import { useSSE } from "../hooks/useSSE";
import TaskBoard from "../components/TaskBoard";
import LogViewer from "../components/LogViewer";
import ModelPicker from "../components/ModelPicker";

type Project = {
  id: number;
  slug: string;
  status: string;
  active_model: string;
  pending_model?: string;
};

type LMStatus = { model: string | null; status: string };

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = Number(id);
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [lmStatus, setLmStatus] = useState<LMStatus | null>(null);
  const lmIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const events = useSSE(projectId);

  useEffect(() => {
    getProject(projectId).then(setProject);
  }, [projectId]);

  useEffect(() => {
    const last = events.at(-1);
    if (last?.type === "completed" || last?.type === "done") {
      getProject(projectId).then(setProject);
    }
  }, [events]);

  const isDone = events.some((e) => e.type === "done");

  // Poll LM Studio status when active provider is lmstudio and project is not done
  useEffect(() => {
    if (!project || project.active_model !== "lmstudio" || isDone) {
      if (lmIntervalRef.current) clearInterval(lmIntervalRef.current);
      return;
    }
    const poll = () => getLMStudioStatus().then(setLmStatus).catch(() => {});
    poll();
    lmIntervalRef.current = setInterval(poll, 5_000);
    return () => {
      if (lmIntervalRef.current) clearInterval(lmIntervalRef.current);
    };
  }, [project?.active_model, isDone]);

  const handleDelete = async () => {
    if (!project) return;
    try {
      await deleteProject(project.id);
      navigate("/");
    } catch {
      setConfirmDelete(false);
    }
  };

  if (!project) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <span className="text-gray-500">Loading…</span>
      </div>
    );
  }

  const activeTask =
    [...events].reverse().find((e) => e.type === "started")?.task ?? "";

  const lmBadgeColor = lmStatus?.status === "ready" ? "text-green-400" : "text-red-400";
  const lmBadgeLabel = lmStatus ? `● ${lmStatus.status}` : null;

  return (
    <div className="min-h-screen bg-gray-950 text-white flex flex-col">
      {/* Top nav */}
      <div className="flex items-center justify-between px-6 py-3 bg-gray-900 border-b border-gray-800 shrink-0">
        <Link to="/" className="text-yellow-400 font-bold hover:text-yellow-300 transition-colors">
          ⚡ ORS
        </Link>
        <span className="text-gray-400 text-sm truncate max-w-xs">{project.slug}</span>
        <div className="flex items-center gap-3">
          <ModelPicker
            projectId={projectId}
            activeModel={project.active_model}
            pendingModel={project.pending_model}
          />
          {lmBadgeLabel && (
            <span className={`text-xs ${lmBadgeColor}`} title={lmStatus?.model ?? ""}>
              {lmBadgeLabel}
            </span>
          )}
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

          {/* Delete */}
          {confirmDelete ? (
            <div className="flex items-center gap-1 text-xs">
              <span className="text-gray-300">Delete?</span>
              <button onClick={handleDelete} className="text-red-400 hover:text-red-300 font-medium">Yes</button>
              <button onClick={() => setConfirmDelete(false)} className="text-gray-400 hover:text-gray-200">No</button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              disabled={project.status === "running"}
              className="text-gray-500 hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed text-sm font-bold transition-colors"
              title={project.status === "running" ? "Can't delete a running project" : "Delete project"}
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex gap-6 p-6 flex-1 overflow-hidden">
        <TaskBoard
          events={events}
          activeModel={project.active_model}
          pendingModel={project.pending_model}
        />
        <LogViewer events={events} activeTask={activeTask} />
      </div>

      {/* Done banner */}
      {isDone && (
        <div className="px-6 pb-4 shrink-0">
          <div className="bg-green-950 border border-green-700 rounded-lg px-4 py-3 text-green-300 text-sm">
            ✓ Build complete — files written to{" "}
            <code className="text-green-200">workspace/{project.slug}/</code>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify build passes**

```
cd frontend && npm run build
```
Expected: no TypeScript errors

- [ ] **Step 3: Run full backend test suite one final time**

```
cd F:\PROJECTS\ORS && pytest tests/ -v
```
Expected: all pass

- [ ] **Step 4: Commit**

```
git add frontend/src/pages/Project.tsx
git commit -m "feat: Project page delete button and LM Studio status badge"
```

---

## Final verification checklist

- [ ] `pytest tests/ -v` — all green
- [ ] `cd frontend && npm run build` — no TypeScript errors
- [ ] Start backend: `uvicorn backend.main:app --reload`
- [ ] Start frontend: `cd frontend && npm run dev`
- [ ] Create a project → verify `workspace/<slug>/_ors/clarify.json` appears after clarify step
- [ ] Gallery: create two projects with same spec (should succeed — slug includes timestamp)
- [ ] Gallery: delete a non-running project → card disappears
- [ ] Gallery: try to delete a running project → button disabled / 409 message
- [ ] Project page: LM Studio badge shows `● ready` or `● unavailable`
- [ ] Project page: with 4-worker parallel generate, TaskBoard shows Worker 1–4 sub-rows during generate step
