# ⚡ ORS — Orchestration System

A personal multi-agent AI system that generates complete Next.js web apps from a natural-language prompt or spec file.

Describe what you want to build → a crew of AI agents clarifies requirements, designs the architecture, writes all the code, reviews it, and fixes any issues — all visible in real time via a live task board in the browser.

---

## Features

- **Five specialized agents** — Clarifier, Architect, FileWriter, Reviewer, Fixer run in sequence under a Supervisor
- **Parallel file generation** — the generate step splits work across multiple concurrent workers when the Architect returns a structured file plan, one worker per file chunk up to the provider's concurrency limit
- **Live task board** — real-time progress streamed via SSE; shows per-worker sub-rows during parallel generate
- **Multi-provider support** — OpenAI, Anthropic, Gemini, and LM Studio (local) with per-provider concurrency config
- **LM Studio status badge** — live ● ready / ● unavailable indicator in the project view
- **Mid-session model switching** — swap models between tasks without losing progress
- **SQLite checkpointing** — crash or close; the supervisor resumes from the last completed task
- **Per-step output files** — each pipeline step writes its output to `workspace/<slug>/_ors/` for inspection and debugging
- **Delete projects** — remove any non-running project from the gallery or project view; deletes the DB record and workspace directory
- **Gallery auto-refresh** — project cards update every 10 seconds while any project is running
- **Spec file upload** — upload `.txt`, `.md`, or `.yaml` files instead of typing
- **Provider-aware retry** — local models auto-retry silently; cloud models pause for approval

---

## Quick Start

### 1. Clone and install

```bash
git clone <repo>
cd ORS
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 2. Configure

Copy and edit `config.yaml` (it is git-ignored):

```yaml
default_model: lmstudio       # starting provider for new projects
retry_policy: auto            # auto | pause | hybrid

providers:
  lmstudio:
    base_url: http://localhost:1234/v1
    default_model: qwen2.5-coder   # ← the model loaded in LM Studio
    concurrency: 4                 # parallel generate workers
  openai:
    api_key: sk-...
    default_model: gpt-4o-mini
    concurrency: 4
  anthropic:
    api_key: sk-ant-...
    default_model: claude-sonnet-4-6
    concurrency: 4
  gemini:
    api_key: AIza...
    default_model: gemini-2.0-flash
    concurrency: 2
```

See [User Manual](MANUAL.md) for full configuration details.

### 3. Run

```bash
# Terminal 1 — backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open **http://localhost:5173** in your browser.

---

## Project Structure

```
ORS/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── database.py              # SQLAlchemy engine + session
│   ├── models.py                # Project, Checkpoint, ProviderConfig ORM models
│   ├── event_bus.py             # In-memory SSE pub/sub
│   ├── workspace_manager.py     # Read/write generated project files
│   ├── api/
│   │   ├── projects.py          # POST/GET/DELETE /projects, background supervisor launch
│   │   ├── stream.py            # GET /projects/{id}/stream (SSE)
│   │   └── settings.py          # PUT /projects/{id}/model, GET /providers/lmstudio/status
│   ├── providers/
│   │   ├── base.py              # Abstract LLMProvider interface
│   │   ├── router.py            # Model selection + task-boundary hot-swap
│   │   ├── lmstudio_provider.py
│   │   ├── openai_provider.py
│   │   ├── anthropic_provider.py
│   │   └── gemini_provider.py
│   └── orchestrator/
│       ├── supervisor.py        # Main agent loop, parallel generate, checkpoint resume
│       ├── crew.py              # CrewAI Task factory functions (including chunk tasks)
│       ├── checkpoint.py        # Save/load task output to SQLite
│       └── agents/              # clarifier, architect, file_writer, reviewer, fixer
├── frontend/
│   └── src/
│       ├── pages/               # Gallery (with delete + polling), NewProject, Project
│       ├── components/          # TaskBoard (with worker sub-rows), LogViewer, ModelPicker
│       ├── hooks/useSSE.ts      # SSE event hook (StepEvent | WorkerEvent union)
│       └── api/client.ts        # Typed fetch wrappers
├── workspace/                   # Generated projects land here
│   └── <slug>/
│       ├── _ors/                # Per-step pipeline outputs (clarify.json, generate.md, …)
│       └── <generated files>
├── config.yaml                  # API keys + model config (git-ignored)
├── requirements.txt
└── ors.db                       # SQLite state database (git-ignored)
```

---

## Tests

```bash
python -m pytest tests/ -v
```

33 tests covering models, workspace, providers, router, checkpoint, API endpoints, and crew task builders.

---

## License

Personal use.
