# ORS User Manual

## Table of Contents

1. [Configuration](#1-configuration)
2. [Starting ORS](#2-starting-ors)
3. [Creating a Project](#3-creating-a-project)
4. [The Project View](#4-the-project-view)
5. [Switching Models Mid-Run](#5-switching-models-mid-run)
6. [Checkpoint Resume](#6-checkpoint-resume)
7. [Retry Policy](#7-retry-policy)
8. [Finding Generated Files](#8-finding-generated-files)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Configuration

All configuration lives in **`config.yaml`** at the project root. This file is git-ignored so your API keys are never committed.

```yaml
default_model: lmstudio       # which provider new projects start with
retry_policy: auto            # see section 7

providers:
  lmstudio:
    base_url: http://localhost:1234/v1
    default_model: qwen2.5-coder
  openai:
    api_key: sk-...
    default_model: gpt-4o-mini
  anthropic:
    api_key: sk-ant-...
    default_model: claude-sonnet-4-6
  gemini:
    api_key: AIza...
    default_model: gemini-2.0-flash
```

### Changing the LM Studio model

The model ORS sends to LM Studio is set by:

```yaml
providers:
  lmstudio:
    default_model: qwen2.5-coder   # ← change this
```

Set it to whatever model is currently loaded in LM Studio. The value must match the model name exactly as LM Studio reports it (visible in the LM Studio UI under the loaded model name). Examples:

| Model | `default_model` value |
|---|---|
| Qwen 2.5 Coder 7B | `qwen2.5-coder` |
| DeepSeek Coder V2 Lite | `deepseek-coder-v2-lite-instruct` |
| Mistral 7B Instruct | `mistral-7b-instruct` |
| Llama 3.2 3B | `llama-3.2-3b-instruct` |

**Important:** Restart the backend after editing `config.yaml` — the file is read once at startup per project.

### LM Studio server URL

By default ORS connects to `http://localhost:1234/v1` (LM Studio's default). If you changed LM Studio's port, update `base_url` accordingly.

### Cloud provider API keys

| Provider | Where to get the key |
|---|---|
| OpenAI | https://platform.openai.com/api-keys |
| Anthropic | https://console.anthropic.com/settings/keys |
| Gemini | https://aistudio.google.com/app/apikey |

Leave the `api_key` field empty (`""`) for any provider you don't use.

### Choosing a specific cloud model

To use a different model for a cloud provider, change its `default_model`:

```yaml
providers:
  anthropic:
    default_model: claude-opus-4-7   # upgrade to Opus
  openai:
    default_model: gpt-4o            # upgrade to full GPT-4o
  gemini:
    default_model: gemini-2.5-pro    # upgrade to Pro
```

---

## 2. Starting ORS

**Backend** (runs on port 8000):

```bash
uvicorn backend.main:app --reload --port 8000
```

On first run this creates `ors.db` (SQLite) in the project root.

**Frontend** (runs on port 5173):

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**.

---

## 3. Creating a Project

### Via the browser

1. Click **+ New Project** on the Gallery page (or navigate to `/new`).
2. Choose your starting model from the dropdown.
3. Either type your spec or upload a file.
4. Click **Build →** (or press Ctrl+Enter).

#### Typing a spec

Write a plain-English description of what you want built. Be as specific or as vague as you like — the Clarifier agent will ask follow-up questions before any code is written.

Example:
> Build a restaurant reservation dashboard. Staff can view, add, edit, and cancel reservations. There's a calendar view by day/week and a list view with search by name or date. Store reservations in SQLite.

#### Uploading a spec file

Click **↑ Upload spec** and select a `.txt`, `.md`, `.yaml`, or `.json` file. The file content is read into the textarea — you can edit it before submitting. Accepted formats:

- **Plain text / Markdown** — freeform description
- **YAML** — structured spec with fields like `name`, `features`, `constraints`
- **JSON** — same as YAML

The filename appears as a badge in the corner of the textarea. Click **×** to clear it and start over.

#### Model selection

The dropdown on the new project form sets which provider the project starts with. This overrides `default_model` from `config.yaml` for this specific project. You can switch models again while the project is running (see section 5).

### Via the API

```bash
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"spec": "Build a todo app with tags and due dates", "model": "anthropic"}'
```

Response: `{"id": 1, "slug": "build-a-todo-app-with-tags", "status": "running"}`

---

## 4. The Project View

Navigate to `/projects/{id}` to see a running project.

### Task board (left panel)

Shows the five stages of a build:

| Stage | What it does |
|---|---|
| **Clarify** | Asks focused questions to produce a structured spec |
| **Architect** | Chooses tech stack and database, creates a file plan |
| **Generate** | Writes all code files according to the plan |
| **Review** | Checks generated code for errors and missing pieces |
| **Fix** | Applies targeted patches based on the review |

Each card shows its current state:

- **Pending** (dim) — not started yet
- **Running** (yellow, pulsing) — active right now
- **Done** (green) — completed successfully
- **Paused** (orange) — waiting for your approval (cloud model, review found issues)
- **Failed** (red) — max fix iterations reached without passing review

### Log viewer (right panel)

Shows all SSE events grouped by task, newest at the top. Click any task header to expand or collapse its log. The currently active task starts expanded.

Each log entry shows the event type (`started`, `completed`, `paused`, etc.) and any output snippet.

### Status indicator (top right)

- **● Running** (green) — build is in progress
- **✓ Done** (blue) — build finished; files are in `workspace/<slug>/`
- **✗ Failed** (red) — build stopped; check the log for details

### Done banner

When the build completes, a green banner appears at the bottom showing the workspace path. The generated files are ready at `workspace/<slug>/` relative to the ORS root.

---

## 5. Switching Models Mid-Run

You can change the active model at any point during a build. The switch takes effect at the **next task boundary** — the currently running task always finishes with the model it started with.

### Via the browser

Use the model dropdown in the top navigation bar of the project view. Select any provider; a badge appears on the task board:

> ⚑ Switching to openai at next task

Once the current task completes, the new model becomes active for all subsequent tasks.

### Via the API

```bash
curl -X PUT http://localhost:8000/projects/1/model \
  -H "Content-Type: application/json" \
  -d '{"model": "openai"}'
```

### Common switching pattern

Start cheap with LM Studio for generation (free, no tokens), then switch to Claude or GPT-4o for the Review + Fix stages where quality matters:

1. Create project with **LM Studio**
2. Let Clarify + Architect + Generate run
3. Switch to **Anthropic** before Review starts
4. Review and Fix run with Claude

---

## 6. Checkpoint Resume

Every time a task completes, its output is saved to `ors.db`. If the backend crashes or you restart it, the supervisor checks for saved checkpoints and skips any task that already has one.

To resume: simply restart the backend and reload the project page. The task board will pick up where it left off.

**Note:** Checkpoint data is stored as JSON in the `checkpoints` table. If you want to force a task to re-run from scratch, you can delete its checkpoint row directly in SQLite:

```bash
sqlite3 ors.db "DELETE FROM checkpoints WHERE project_id=1 AND task_name='generate';"
```

---

## 7. Retry Policy

When the Reviewer finds issues, the Supervisor decides whether to auto-fix or pause for your approval. This is controlled by `retry_policy` in `config.yaml`.

| Policy | Local model (LM Studio) | Cloud model |
|---|---|---|
| `auto` | Retries silently (up to 3×) | Retries silently (up to 3×) |
| `pause` | Pauses, shows issues in UI | Pauses, shows issues in UI |
| `hybrid` | Retries silently | Pauses for approval |

**`hybrid` is recommended** if you mix local and cloud models. You get fast silent retries when running locally (cheap), but a chance to intervene when burning cloud tokens.

Change the policy:

```yaml
retry_policy: hybrid
```

Restart the backend to apply.

---

## 8. Finding Generated Files

Generated projects are written to:

```
workspace/<project-slug>/
```

For example, a project with slug `build-a-todo-app` produces:

```
workspace/
└── build-a-todo-app/
    ├── app/
    │   ├── page.tsx
    │   ├── layout.tsx
    │   └── api/
    │       └── tasks/
    │           └── route.ts
    ├── components/
    │   └── TaskList.tsx
    ├── prisma/
    │   └── schema.prisma
    └── package.json
```

The generated code is a standard Next.js 14+ app. To run it:

```bash
cd workspace/build-a-todo-app
npm install
npm run dev
```

---

## 9. Troubleshooting

### LM Studio: "Connection refused" or timeout

- Make sure LM Studio is running and the local server is started (green indicator in LM Studio's top bar).
- Check the port: LM Studio defaults to `1234`. Verify `base_url` in `config.yaml` matches.
- Make sure a model is loaded in LM Studio before starting a build.

### LM Studio: Wrong model being used

The `default_model` in `config.yaml` must match the model identifier LM Studio uses internally, not the display name. To find the exact identifier:

1. In LM Studio, load your model.
2. Make a test request: `curl http://localhost:1234/v1/models`
3. Use the `id` field from the response as `default_model`.

### "API key invalid" for cloud providers

Double-check the key in `config.yaml`. Keys are read fresh for each new project — you don't need to restart the backend after changing them, but you do need to start a new project.

### Build stuck on a task

Check the backend terminal for Python tracebacks. Common causes:
- Model returned malformed output (especially `=== FILE: ===` parsing failures) — try a different model or add more detail to your spec.
- LM Studio ran out of context — use a model with a longer context window or split the spec into smaller projects.

### Resuming after a crash loses some progress

Checkpoints are saved after each **completed** task. If the backend crashed mid-task, that task's output was not saved and it will re-run from the beginning. This is expected.

### Frontend shows blank task board after refresh

The task board is populated by SSE events received since the page loaded. Past events are not replayed. Reload the project state by navigating away and back — the project status card shows the last known `active_model` and `status` from the database.
