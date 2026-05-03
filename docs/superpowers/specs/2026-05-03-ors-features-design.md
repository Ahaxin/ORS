# ORS Feature Pack: Delete, Status, LM Studio Health, Step Files, Parallel Generate

**Date:** 2026-05-03  
**Status:** Approved  
**Scope:** Five additive features on top of the existing ORS FastAPI + React stack

---

## 1. Delete Project

### Backend
- New endpoint: `DELETE /projects/{id}` in `backend/api/projects.py`
- Returns HTTP 204
- Deletes DB row (SQLAlchemy cascade `all, delete-orphan` removes `Checkpoint` rows automatically)
- Calls `shutil.rmtree(workspace/<slug>)` if the directory exists — no error if already gone
- Raises 404 if project not found

### Frontend
- **Gallery**: each card shows a `×` button in the top-right corner, visible on hover
  - Clicking shows inline confirmation: "Delete? [Yes] [No]" — no modal
  - On Yes: calls `DELETE /projects/{id}`, removes card from local state immediately
- **Project page**: delete button in top nav
  - Same inline confirmation
  - On confirm: deletes then navigates to `/`
- New API client function: `deleteProject(id: number): Promise<void>`

---

## 2. Per-Step Output Files

After each pipeline step completes, `Supervisor` writes the step's primary output to `workspace/<slug>/_ors/<step>.json`.

| Step | File | Content |
|------|------|---------|
| clarify | `_ors/clarify.json` | `{ "refined_spec": "..." }` |
| architect | `_ors/architect.json` | `{ "plan": "..." }` |
| generate | `_ors/generate.md` | raw file-block output |
| review | `_ors/review.json` | `{ "result": "PASS" \| issues }` |
| fix | `_ors/fix.md` | corrected file-block output |

### Implementation
- Add `write_json(path, data)` and `write_text(path, text)` helpers to `WorkspaceManager`
  - `write_json` serialises with `json.dumps(indent=2)`
- `Supervisor.run()` calls the appropriate helper immediately after each `ckpt.save()`
- Files are written even on cache hits (re-hydrate from checkpoint data)

---

## 3. LM Studio Model Status

### Backend
- New endpoint: `GET /providers/lmstudio/status` in `backend/api/settings.py`
- Uses `httpx.AsyncClient` (already a FastAPI dep) to call `GET {lmstudio_base_url}/models`
- Parses response: if a model entry has `state == "loaded"` → `"ready"`; if loaded but busy → `"busy"`; unreachable or no model → `"unavailable"`
- Returns `{ model: str | null, status: "ready" | "busy" | "unavailable" }`
- Reads `base_url` from `config.yaml` via `ProviderRouter.from_config_file()`

### Frontend
- In `Project.tsx`, when `project.active_model === "lmstudio"`:
  - Poll `GET /providers/lmstudio/status` every 5 seconds
  - Stop polling when `isDone` is true
- Show a small badge next to the model name in the top nav:
  - `● ready` — green
  - `● busy` — yellow  
  - `● unavailable` — red
- New API client function: `getLMStudioStatus(): Promise<{ model: string | null, status: string }>`

---

## 4. Parallel Generate Step

### Config
Add `concurrency: int` to each provider block in `config.yaml`:

```yaml
providers:
  lmstudio:
    concurrency: 4
  openai:
    concurrency: 4
  anthropic:
    concurrency: 4
  gemini:
    concurrency: 2
```

### Provider layer
- `LLMProvider` base class gains `concurrency: int = 1`
- Each provider constructor reads `concurrency` from its config dict and stores it
- `ProviderRouter.get_provider()` passes the value through

### Supervisor — generate step
1. Parse the architect plan JSON to extract the file list: `plan_data["files"]` → list of `{path, description}`
2. Split into N chunks where `N = min(concurrency, len(files))`
3. Build N `Task` objects (one per chunk) using a new `build_generate_chunk_task(agent, chunk, spec)` in `crew.py`
4. Run N `Crew` instances concurrently:
   ```python
   results = await asyncio.gather(*[
       self._run_worker(i, chunk, spec)
       for i, chunk in enumerate(chunks)
   ])
   ```
5. `_run_worker` emits `worker_started` before kickoff and `worker_completed` after
6. Merge all result strings, call `_write_files` on the combined output

### Worker events (SSE)
New event shape emitted by `_run_worker`:
```json
{ "task": "generate", "type": "worker_started", "worker_id": 1, "files": ["src/app.ts", "src/index.ts"] }
{ "task": "generate", "type": "worker_completed", "worker_id": 1, "files": ["src/app.ts", "src/index.ts"] }
```

### Frontend — TaskBoard
- `useSSE.ts`: extend `TaskEvent` to a discriminated union:
  ```ts
  type StepEvent = { task: string; type: "started"|"completed"|"paused"|"failed"|"done"; ... }
  type WorkerEvent = { task: "generate"; type: "worker_started"|"worker_completed"; worker_id: number; files: string[] }
  export type TaskEvent = StepEvent | WorkerEvent;
  ```
- `TaskBoard`: when the generate row is active, render sub-rows — one per `worker_id` seen in events
  - Each sub-row: `Worker {n}: {files joined by ", "} ● running` or `● done`
  - Sub-rows collapse to a single summary line once all workers have `worker_completed`

---

## 5. Gallery Status Refresh

- While any project in the list has `status === "running"`, poll `GET /projects` every 10 seconds
- Stop polling when all projects are non-running or component unmounts
- Keeps Gallery cards current without requiring navigation

---

## Affected Files

| File | Change |
|------|--------|
| `backend/api/projects.py` | Add `DELETE /projects/{id}` |
| `backend/api/settings.py` | Add `GET /providers/lmstudio/status` |
| `backend/workspace_manager.py` | Add `write_json`, `write_text` helpers |
| `backend/orchestrator/supervisor.py` | Per-step file writes; parallel generate |
| `backend/orchestrator/crew.py` | Add `build_generate_chunk_task` |
| `backend/providers/base.py` | Add `concurrency` field |
| `backend/providers/*.py` | Read `concurrency` from config |
| `backend/providers/router.py` | Pass `concurrency` through |
| `config.yaml` | Add `concurrency` per provider |
| `frontend/src/api/client.ts` | Add `deleteProject`, `getLMStudioStatus` |
| `frontend/src/hooks/useSSE.ts` | Extend `TaskEvent` union |
| `frontend/src/pages/Gallery.tsx` | Delete button; polling refresh |
| `frontend/src/pages/Project.tsx` | Delete button; LM Studio badge |
| `frontend/src/components/TaskBoard.tsx` | Worker sub-rows in generate |

---

## Out of Scope

- Parallel execution for clarify / architect / review / fix steps (sequential dependencies make this unsafe)
- LM Studio status for other providers (OpenAI/Anthropic have their own health mechanisms)
- Undo / soft-delete for projects
