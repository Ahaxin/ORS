# Checkpoint Resume & Model Output Visibility

**Date:** 2026-05-03  
**Status:** Approved

## Problem

Long runs (1+ hour) using a local LM Studio model fail when the computer hibernates. The root cause is that hibernation severs the TCP connection between the ORS backend and LM Studio. LM Studio's health check (`GET /v1/models`) still returns green, so the system appears healthy, but actual completion calls hang indefinitely on the dead socket. The project stays in `running` status with no progress, and the user cannot tell what happened or resume from where the run stopped.

Additionally, when generate fails, all parallel worker progress is lost because the entire generate step is saved as a single checkpoint only after all workers finish.

## Goals

1. Detect hung LM Studio calls and fail gracefully within a bounded time.
2. Save per-worker progress so a resumed run skips completed workers.
3. Allow the user to resume a stalled or failed project from the last completed checkpoint.
4. Write model output to a log file so the user can see what was generated.

## Out of Scope

- Streaming model output live in the UI (file log is sufficient).
- Automatic resume on server restart (user-triggered resume only).
- Changing the review/fix loop checkpoint granularity.

---

## Architecture

Five focused changes:

| Component | Change |
|---|---|
| `config.yaml` | Add `timeout_minutes` per provider |
| `backend/orchestrator/supervisor.py` | Per-worker checkpoints, timeout, output log |
| `backend/models.py` | Add `stalled` to valid project statuses |
| `backend/api/projects.py` | Add `POST /projects/{id}/resume` endpoint |
| `frontend/src/pages/Project.tsx` + `frontend/src/api/client.ts` | Resume button, stalled badge, log links |
| `frontend/src/pages/Gallery.tsx` | Stalled badge |

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

Default for all providers: `10` minutes. Cloud providers can set it higher (e.g., `30`).

### 2. Per-Worker Checkpoints

**Current behavior:** A single `generate` checkpoint is saved only after all workers finish. If any worker hangs, nothing is saved.

**New behavior:** Each worker saves its own checkpoint immediately on completion, using task name `generate_worker_{i}`. The final merged `generate` checkpoint is still saved after all workers finish (for backward compatibility with the existing resume logic).

Resume logic in `_run_generate`:
1. For each worker index `i`, check if `generate_worker_{i}` checkpoint exists.
2. If yes — load its output, skip re-running.
3. If no — run the worker.
4. Gather only the missing workers in parallel.
5. Merge cached + new outputs in worker-index order.

### 3. Timeout

Each worker call is wrapped with `asyncio.wait_for(timeout=provider.timeout_seconds)`. On `asyncio.TimeoutError`:
- The worker raises, which propagates out of `asyncio.gather`.
- The supervisor catches it, emits `{"task": "generate", "type": "stalled", "message": "..."}`.
- The supervisor updates the project status to `stalled` in the DB and returns.
- Workers that already completed have their checkpoints saved and are safe.

### 4. `stalled` Project Status

Add `stalled` as a valid `Project.status` value (alongside `pending`, `running`, `done`, `failed`, `paused`).

- `stalled` = timed out or otherwise hung, but checkpoints are intact and the project **can be resumed**.
- `failed` = unrecoverable error (e.g., malformed plan, provider error). Cannot resume.
- The delete endpoint already allows deleting non-`running` projects, so stalled projects can be deleted normally.

### 5. Resume Endpoint

```
POST /projects/{id}/resume
```

- Returns `409` if status is not `stalled` or `failed`.
- Sets `project.status = "running"`.
- Enqueues `_run(project_id, slug, spec_text, active_model, db)` as a background task.
- The supervisor's existing checkpoint logic skips already-completed steps (clarify, architect).
- The new per-worker checkpoint logic skips already-completed workers inside generate.

### 6. Model Output Log

After each step completes, its raw model output is appended to `_ors/run_log.txt`:

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
```

The generate workers also write to `_ors/generate_log.txt` (generate-only, for easy access when only the generate step needs inspection).

Both files are appended incrementally, so partial runs produce partial logs.

---

## Frontend Changes

### Status Badge

The top-right status area in `Project.tsx` gains a `stalled` case:

| Status | Display |
|---|---|
| running | `● Running` (green) |
| stalled | `⚠ Stalled` (orange) |
| failed | `✗ Failed` (red) |
| done | `✓ Done` (blue) |

### Resume Button

Shown next to the status badge when `project.status === "stalled" || "failed"`. Calls `POST /projects/{id}/resume`. While the request is in flight, the button shows `Resuming…` and is disabled. On success, status resets to `running` and the SSE stream reconnects.

### Log Links

When status is `stalled`, `failed`, or `done`, show links in the bottom banner:
- `View run log` → `workspace/{slug}/_ors/run_log.txt`
- `View generate log` → `workspace/{slug}/_ors/generate_log.txt` (only if generate has run)

The backend already serves the workspace directory statically.

### Gallery

Stalled projects show `⚠ stalled` in orange instead of `● running` in green.

---

## Data Flow — Resume Scenario

```
User wakes computer
  → LM Studio health check: ● ready (model list works)
  → Backend: worker 2 asyncio.wait_for fires after 10 min
  → Supervisor: catches TimeoutError
      → emits generate/stalled event
      → sets project.status = "stalled"
  → UI: status badge → ⚠ Stalled, Resume button appears
  → User clicks Resume
      → POST /projects/{id}/resume
      → supervisor re-runs:
          clarify  → checkpoint found, skip
          architect → checkpoint found, skip
          generate:
            worker 0 → checkpoint found, skip
            worker 1 → checkpoint found, skip
            worker 2 → no checkpoint, re-run  ✓
            worker 3 → no checkpoint, re-run  ✓
      → continues to review/fix/done
```

---

## Success Criteria

- A run that hangs on generate marks itself `stalled` within `timeout_minutes` of the hang.
- Clicking Resume skips all completed steps and workers.
- `_ors/run_log.txt` contains the raw model output for every completed step.
- The UI shows the correct status badge and Resume button for stalled/failed projects.
- Existing runs (no stalled state) continue to work without any change.
