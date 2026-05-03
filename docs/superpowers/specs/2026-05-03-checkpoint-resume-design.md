# Checkpoint Resume & Model Output Visibility

**Date:** 2026-05-03  
**Status:** Draft

## Problem

Long runs (1+ hour) using a local LM Studio model fail when the computer hibernates. The root cause is that hibernation severs the TCP connection between the ORS backend and LM Studio. LM Studio's health check (`GET /v1/models`) still returns green, so the system appears healthy, but actual completion calls hang indefinitely on the dead socket. The project stays in `running` status with no progress, and the user cannot tell what happened or resume from where the run stopped.

Additionally, when generate fails, all parallel worker progress is lost because the entire generate step is saved as a single checkpoint only after all workers finish.

## Goals

1. Detect hung LM Studio calls and fail gracefully within a bounded time.
2. Save per-worker progress so a resumed run skips completed workers.
3. Allow the user to resume a stalled or paused project from the last completed checkpoint.
4. Write model output to a log file so the user can see what was generated.
5. Ensure projects stuck in `running` after a server restart can be recovered.

## Out of Scope

- Streaming model output live in the UI (file log is sufficient).
- Automatic resume on server restart (user-triggered resume only, but orphaned `running` projects are reset to `stalled` on startup).
- Changing the review/fix loop checkpoint granularity.
- Allowing `concurrency` to change between a stalled run and its resume (documented constraint, not enforced in code).

---

## Architecture

Six focused changes:

| Component | Change |
|---|---|
| `config.yaml` | Add `timeout_minutes` per provider |
| `backend/orchestrator/supervisor.py` | Per-worker checkpoints, timeout, output log, status writes |
| `backend/models.py` | Add `stalled` to valid project statuses |
| `backend/api/projects.py` | Add `POST /projects/{id}/resume` endpoint |
| `backend/main.py` | Startup hook: reset orphaned `running` projects to `stalled` |
| `frontend/src/pages/Project.tsx` + `frontend/src/api/client.ts` | Resume button, stalled badge, log links |
| `frontend/src/pages/Gallery.tsx` | Stalled/paused badge |

---

## Backend Changes

### 1. Config — `timeout_minutes`

Add `timeout_minutes` to each provider block in `config.yaml`. The provider router reads this and exposes it as `provider.timeout_seconds`.

```yaml
lmstudio:
  base_url: http://localhost:1234/v1
  default_model: gemma-4-26b-a4b-it-uncensored
  concurrency: 4
  timeout_minutes: 10   # new — per-call timeout for completion requests
```

Default for all providers: `10` minutes. Cloud providers can set higher values.

Add `timeout_seconds: int` to the `LLMProvider` base class, defaulting to `600`. `ProviderRouter.get_provider()` sets it from `cfg.get('timeout_minutes', 10) * 60` after constructing the provider instance.

### 2. Project Status Transitions

The supervisor is responsible for writing `project.status` to the DB. It already holds a `db: Session` via `CheckpointManager`. The supervisor will query `db.get(Project, project_id)` and update `status` directly at each transition:

| Transition | Trigger |
|---|---|
| `running` → `stalled` | `asyncio.TimeoutError` caught in `run()` |
| `running` → `done` | Final `done` event emitted |
| `running` → `paused` | Review step emits `paused` and supervisor returns early |

`failed` status is reserved for unrecoverable errors (e.g., no plan could be parsed from architect output). The resume endpoint does **not** accept `failed` — failed projects must be deleted and re-created.

### 3. Per-Worker Checkpoints

**Current behavior:** A single `generate` checkpoint is saved only after all workers finish. If any worker hangs, nothing is saved.

**New behavior:** Each worker saves its own checkpoint immediately on completion, using task name `generate_worker_{i}`. The final merged `generate` checkpoint is still saved after all workers finish (for the combined output used by review/fix).

Resume logic in `_run_generate`:
1. For each worker index `i`, check if `generate_worker_{i}` checkpoint exists.
2. If yes — load its output, skip re-running. Write a skipped entry to the log.
3. If no — run the worker.
4. Gather only the missing workers in parallel.
5. Merge cached + new outputs in worker-index order.

**Constraint:** `concurrency` must not change between a stalled run and its resume. If it does, worker indices will map to different file chunks and cached outputs will be wrong. This is a documented operator constraint, not enforced in code.

### 4. Timeout

Each individual worker call is wrapped with its own `asyncio.wait_for(timeout=provider.timeout_seconds)`. Timeouts are per-worker, not on the entire `asyncio.gather` call.

On `asyncio.TimeoutError` in any worker:
- That worker raises `TimeoutError`, which propagates out of `asyncio.gather` and cancels any still-running sibling workers.
- Sibling workers that had not yet completed do **not** get their `generate_worker_{i}` checkpoint saved (they were cancelled mid-run).
- The supervisor's `run()` catches `TimeoutError`, emits `{"task": "generate", "type": "stalled", "message": "..."}`.
- The supervisor sets `project.status = "stalled"` in the DB and returns.
- Workers that already completed before the timeout have their `generate_worker_{i}` checkpoints saved and are safe.

The SSE stream is **not** closed on stall — the backend only closes the stream on `type == "done"`. The stalled event causes the frontend to update the status badge; no stream reconnect is needed.

### 5. `stalled` Project Status

Add `stalled` as a valid `Project.status` value.

| Status | Meaning | Can resume? | Can delete? |
|---|---|---|---|
| `running` | Active background task | No | No |
| `stalled` | Timed out, checkpoints intact | Yes | Yes |
| `paused` | Review waiting for user approval | Yes | Yes |
| `failed` | Unrecoverable error | No | Yes |
| `done` | Completed successfully | No | Yes |

### 6. Resume Endpoint

```
POST /projects/{id}/resume
```

- Returns `404` if the project does not exist.
- Returns `409` if `project.status` is not `stalled` or `paused`.
- Sets `project.status = "running"`.
- Enqueues `_run(project_id, slug, spec_text, active_model, db)` as a background task, where `db` comes from the resume endpoint's own `Depends(get_db)` injection (not reused from any prior request). This follows the same pattern as the existing `create_project` endpoint, which also passes a request-scoped session to a background task. Both share the same known trade-off: the session is bound to the HTTP request scope. This is acceptable given the existing codebase already works this way.
- The supervisor's existing step-level checkpoint logic skips clarify and architect if their checkpoints exist.
- The new per-worker checkpoint logic skips completed workers inside generate.

### 7. Startup Hook — Reset Orphaned `running` Projects

In `backend/main.py`, the `lifespan` context manager runs a startup query:

```python
db.query(Project).filter_by(status="running").update({"status": "stalled"})
db.commit()
```

This handles the case where the server restarts while a project is running (e.g., after a reboot). The project appears `stalled` in the UI and can be resumed. Without this, the project is stuck in `running` forever — the user cannot delete or resume it.

### 8. Model Output Log

After each step completes, its raw model output is appended to `_ors/run_log.txt`. Workers that are skipped on resume write a marker instead of their output.

`WorkspaceManager` gains a new `append_text(path, content)` method that opens the file in append mode (`'a'`) rather than overwriting.

Log format:

```
=== CLARIFY — 2026-05-03 14:20:01 ===
<refined spec text>

=== ARCHITECT — 2026-05-03 14:21:45 ===
<plan JSON>

=== WORKER 0 — 2026-05-03 14:35:12 ===
Files: src/app.tsx, src/utils.ts
---
=== FILE: src/app.tsx ===
...generated code...

=== WORKER 1 — skipped (checkpoint) ===
Files: src/lib/utils.ts
```

Skipped entries intentionally omit the timestamp since no new model call occurred.

`run_log.txt` includes all step outputs including generate worker entries. `generate_log.txt` is a strict subset: it contains only the worker entries from the generate step (same format, same content), written in parallel with `run_log.txt`. Both files accumulate across resume cycles so the full history of a project's runs is preserved.

---

## Frontend Changes

### Status Badge

The top-right status area in `Project.tsx` gains `stalled` and `paused` cases:

| Status | Display |
|---|---|
| running | `● Running` (green) |
| stalled | `⚠ Stalled` (orange) |
| paused | `⏸ Paused` (yellow) |
| failed | `✗ Failed` (red) |
| done | `✓ Done` (blue) |

### Resume Button

Shown next to the status badge when `project.status === "stalled"` or `project.status === "paused"`. Calls `POST /projects/{id}/resume`. While the request is in flight, the button shows `Resuming…` and is disabled. On success, the project status in local state resets to `running` — the existing SSE stream remains open and begins receiving new events.

### Log Links

When status is `stalled`, `failed`, or `done`, show links in the bottom banner:
- `View run log` → `workspace/{slug}/_ors/run_log.txt`
- `View generate log` → `workspace/{slug}/_ors/generate_log.txt` (only if generate has run)

The backend already serves the workspace directory statically.

### Gallery

Stalled projects show `⚠ stalled` in orange. Paused projects show `⏸ paused` in yellow.

---

## Data Flow — Resume Scenario

```
User wakes computer
  → LM Studio health check: ● ready (model list works)
  → Backend: worker 2 asyncio.wait_for fires after 10 min
  → Supervisor: catches TimeoutError
      → emits generate/stalled event
      → sets project.status = "stalled" in DB
      → returns (SSE stream stays open)
  → UI: receives stalled event → status badge → ⚠ Stalled, Resume button appears
  → User clicks Resume
      → POST /projects/{id}/resume
      → project.status = "running"
      → supervisor re-runs with fresh DB session:
          clarify   → checkpoint found, skip
          architect → checkpoint found, skip
          generate:
            worker 0 → generate_worker_0 checkpoint found, skip ✓
            worker 1 → generate_worker_1 checkpoint found, skip ✓
            worker 2 → no checkpoint, re-run  ✓
            worker 3 → no checkpoint, re-run  ✓
      → continues to review/fix/done
```

---

## Success Criteria

- A run that hangs on generate marks itself `stalled` within `timeout_minutes` of the hang.
- Clicking Resume skips all completed steps and workers; only incomplete workers re-run.
- `_ors/run_log.txt` contains the raw model output for every completed step, including skipped-checkpoint markers.
- The UI shows the correct status badge and Resume button for stalled/paused projects.
- Projects stuck in `running` after a server restart are reset to `stalled` on the next startup.
- Existing runs (no stalled state) continue to work without any change.
