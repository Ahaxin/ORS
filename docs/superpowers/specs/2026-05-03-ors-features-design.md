# ORS Feature Pack: Delete, Status, LM Studio Health, Step Files, Parallel Generate

**Date:** 2026-05-03  
**Status:** Approved  
**Scope:** Five additive features on top of the existing ORS FastAPI + React stack

---

## 1. Delete Project

### Backend
- New endpoint: `DELETE /projects/{id}` in `backend/api/projects.py`
- Returns HTTP 409 if `project.status == "running"` (deletion of in-progress projects is unsupported)
- Returns HTTP 404 if project not found
- Returns HTTP 204 on success
- Deletes DB row (SQLAlchemy cascade `all, delete-orphan` removes `Checkpoint` rows automatically)
- Calls `shutil.rmtree(workspace/<slug>)` if the directory exists — swallows `FileNotFoundError`

### Frontend
- **Gallery**: each card shows a `×` button in the top-right corner, visible on hover
  - Clicking shows inline confirmation: "Delete? [Yes] [No]" — no modal
  - On Yes: calls `DELETE /projects/{id}`, removes card from local state immediately
  - If server returns 409, shows "Can't delete a running project" inline
- **Project page**: delete button in top nav
  - Same inline confirmation
  - On confirm: deletes then navigates to `/`
  - Button is disabled (greyed out) when `project.status === "running"`
- New API client function: `deleteProject(id: number): Promise<void>`

---

## 2. Per-Step Output Files

After each pipeline step completes, `Supervisor` writes the step's primary output to `workspace/<slug>/_ors/`.

| Step | File | Content |
|------|------|---------|
| clarify | `_ors/clarify.json` | `{ "refined_spec": "..." }` |
| architect | `_ors/architect.json` | `{ "plan": "..." }` |
| generate | `_ors/generate.md` | merged raw file-block output |
| review | `_ors/review.json` | `{ "result": "PASS" \| issues }` |
| fix (iteration N) | `_ors/fix_1.md`, `_ors/fix_2.md`, … | corrected file-block output per iteration |

The fix loop in `supervisor.py` uses a 0-based index `i`; filenames use `i+1` to be 1-based: `_ors/fix_1.md`, `_ors/fix_2.md`, `_ors/fix_3.md`. Write `ws.write_text(f"_ors/fix_{i+1}.md", files_content)` inside the loop body.

### Implementation
- Add `write_json(relative_path, data)` and `write_text(relative_path, text)` helpers to `WorkspaceManager`
  - `write_json` serialises with `json.dumps(indent=2)`, calls existing `write_file`
  - `write_text` calls existing `write_file` directly
- `Supervisor.run()` calls the appropriate helper immediately after each `ckpt.save()`
- Files are written even on cache hits (re-hydrate from checkpoint data so restarts populate `_ors/`)

---

## 3. LM Studio Model Status

### Backend
- New endpoint: `GET /providers/lmstudio/status` added to `backend/api/settings.py`
- Required new imports in `settings.py`: `httpx`, `ProviderRouter` from `backend.providers.router`
- `httpx` must be present in project dependencies (add to `requirements.txt` / `pyproject.toml` if not already)
- Calls LM Studio's **`GET {base_url}/models`** (OpenAI-compatible list, e.g. `http://localhost:1234/v1/models`)
  - This endpoint returns `{"object": "list", "data": [{"id": "model-name", ...}]}`
  - If `data` is non-empty, the first entry's `id` is the loaded model name → status `"ready"`
  - If `data` is empty → status `"unavailable"` with `model: null`
  - On `httpx` connection error / timeout → status `"unavailable"` with `model: null`
  - Note: LM Studio's `/v1/models` does not expose a busy/idle field. `"busy"` will be inferred in a future iteration if LM Studio exposes it; for now only `"ready"` and `"unavailable"` are emitted.
- Returns `{ model: str | null, status: "ready" | "unavailable" }`
- Reads `base_url` from `config.yaml` via `ProviderRouter.from_config_file().config["providers"]["lmstudio"]["base_url"]`

### Frontend
- In `Project.tsx`, when `project.active_model === "lmstudio"`:
  - Poll `GET /providers/lmstudio/status` every 5 seconds using `setInterval`
  - Clear interval when `isDone` is true or component unmounts
- Show a small badge next to the model name in the top nav:
  - `● ready` — green (`text-green-400`)
  - `● unavailable` — red (`text-red-400`)
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
- `LLMProvider` base class (`backend/providers/base.py`) gains `concurrency: int = 1` as a class-level attribute. Currently `base.py` only declares `is_local`, `name`, and `get_llm` — add `concurrency = 1` so all subclasses inherit it and `router.get_provider().concurrency` never raises `AttributeError`.
- Each provider constructor (`openai_provider.py`, `anthropic_provider.py`, `gemini_provider.py`, `lmstudio_provider.py`) must accept `concurrency: int = 1` and set `self.concurrency = concurrency`.
- `ProviderRouter.get_provider()` (`backend/providers/router.py`) currently passes only `api_key`/`model`/`base_url` to each provider. Add `concurrency=cfg.get("concurrency", 1)` to every `case` branch. Example for openai: `return OpenAIProvider(api_key=cfg["api_key"], model=cfg["default_model"], concurrency=cfg.get("concurrency", 1))`
- `config.yaml` today has **no** `concurrency` keys at all — all four must be added fresh (see Config section above).
- `Supervisor` accesses concurrency via `self.router.get_provider().concurrency`

### Supervisor — generate step
1. Attempt to parse the architect plan as JSON: `json.loads(plan)` to extract `plan_data["files"]` (list of `{path, description}`)
   - **Fallback**: if JSON parsing fails or `"files"` key is absent, fall back to `N=1` (single worker, existing behaviour)
2. Split file list into `N = min(concurrency, len(files))` chunks (round-robin split)
3. Each worker runs its own `Crew` instance via `_run_worker(worker_id, chunk_files, spec)`:
   ```python
   async def _run_worker(self, worker_id: int, files: list, spec: str) -> str:
       await self.emit("generate", "worker_started", {"worker_id": worker_id, "files": [f["path"] for f in files]})
       agent = make_file_writer(self._llm())
       task = build_generate_chunk_task(agent, files, spec)
       crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
       loop = asyncio.get_event_loop()
       result = await loop.run_in_executor(None, crew.kickoff)  # run_in_executor required — crew.kickoff is synchronous
       await self.emit("generate", "worker_completed", {"worker_id": worker_id, "files": [f["path"] for f in files]})
       return result.raw
   ```
4. Run all workers concurrently:
   ```python
   results = await asyncio.gather(*[self._run_worker(i, chunk, spec) for i, chunk in enumerate(chunks)])
   ```
5. Merge results: `files_content = "\n".join(results)`
6. Call `_write_files(files_content)` on merged output
7. Checkpoint the **merged** `files_content` (single checkpoint entry, key `"generate"`)
8. **Cache-hit path**: when `self.ckpt.load(project_id, "generate")` returns a hit, the stored value is already the merged string. The existing cache-hit branch (`_write_files(cached["files_content"])`) is unchanged — no workers are re-spawned on restart.

### `crew.py` addition
New task builder for a file subset:
```python
def build_generate_chunk_task(agent, files: list[dict], spec: str) -> Task:
    file_list = "\n".join(f"- {f['path']}: {f['description']}" for f in files)
    return Task(
        description=(
            f"Generate ONLY these files:\n{file_list}\n\nSpec: {spec}\n\n"
            "Output each file using this EXACT format:\n\n"
            "=== FILE: src/index.ts ===\n"
            "// content\n\n"
            "=== FILE: src/app.ts ===\n"
            "// content\n\n"
            "Do not use placeholder text like <path> or <content>."
        ),
        expected_output="All assigned files with === FILE: <actual path> === headers and full content.",
        agent=agent,
    )
```

### Worker events (SSE)
New event shapes emitted by `_run_worker`:
```json
{ "task": "generate", "type": "worker_started",   "worker_id": 0, "files": ["src/app.ts", "src/index.ts"] }
{ "task": "generate", "type": "worker_completed",  "worker_id": 0, "files": ["src/app.ts", "src/index.ts"] }
```

### Frontend — `useSSE.ts`
Replace the existing single `TaskEvent` type with a discriminated union. No changes are needed to the hook body — `setEvents` is typed `TaskEvent[]` and will accept both shapes once the union type is in place.

```ts
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
```

### Frontend — `TaskBoard`
- `statusOf(task)` must **exclude** `WorkerEvent` entries:
  ```ts
  const isStepEvent = (e: TaskEvent): e is StepEvent =>
    e.type !== "worker_started" && e.type !== "worker_completed";
  const stepEvents = events.filter(isStepEvent);
  // statusOf uses stepEvents, not events
  ```
- When generate row is `"running"`, render worker sub-rows below it — one per `worker_id` seen in `WorkerEvent` entries:
  - `● running` if only `worker_started` seen for that id; `● done` if `worker_completed` seen
  - Display: `Worker {n}: file1.ts, file2.ts`
  - Sub-rows collapse (hidden) once all workers have `worker_completed` and generate step is `"done"`

---

## 5. Gallery Status Refresh

- While any project has `status === "running"`, poll `GET /projects` every 10 seconds
- Use `useEffect` with `setInterval`; clear interval on unmount or when no running projects remain
- Wrap fetch in `try/catch` — log error and continue polling (do not crash component)
- Guard against overlapping requests: skip a tick if the previous fetch is still in flight (use a `ref` flag)

---

## Affected Files

| File | Change |
|------|--------|
| `backend/api/projects.py` | Add `DELETE /projects/{id}` with 409 guard; add `shutil` import |
| `backend/api/settings.py` | Add `GET /providers/lmstudio/status`; add `httpx`, `ProviderRouter` imports |
| `backend/workspace_manager.py` | Add `write_json`, `write_text` helpers |
| `backend/orchestrator/supervisor.py` | Per-step file writes; `_run_worker`; parallel generate |
| `backend/orchestrator/crew.py` | Add `build_generate_chunk_task` |
| `backend/providers/base.py` | Add `concurrency: int = 1` field |
| `backend/providers/openai_provider.py` | Accept + store `concurrency` |
| `backend/providers/anthropic_provider.py` | Accept + store `concurrency` |
| `backend/providers/gemini_provider.py` | Accept + store `concurrency` |
| `backend/providers/lmstudio_provider.py` | Accept + store `concurrency` |
| `backend/providers/router.py` | Read + pass `concurrency` in `get_provider()` |
| `config.yaml` | Add `concurrency` per provider |
| `frontend/src/api/client.ts` | Add `deleteProject`, `getLMStudioStatus` |
| `frontend/src/hooks/useSSE.ts` | Export `StepEvent`, `WorkerEvent`; update `TaskEvent` union |
| `frontend/src/pages/Gallery.tsx` | Delete button; polling refresh with error guard |
| `frontend/src/pages/Project.tsx` | Delete button (disabled when running); LM Studio badge |
| `frontend/src/components/TaskBoard.tsx` | Filter step events for `statusOf`; worker sub-rows |

---

## Out of Scope

- Parallel execution for clarify / architect / review / fix steps (sequential dependencies)
- LM Studio `"busy"` status (not exposed by `/v1/models`; deferred to future iteration)
- Undo / soft-delete for projects
