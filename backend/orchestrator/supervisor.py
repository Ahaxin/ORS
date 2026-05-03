import asyncio
import json
import re
from datetime import datetime, timezone
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

    def _set_status(self, status: str) -> None:
        # Called only from event-loop coroutines (never from executor threads), so session access is safe.
        p = self.ckpt.db.get(Project, self.project_id)
        if p:
            p.status = status
            self.ckpt.db.commit()

    def _ts(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    async def _run(self, task, agent) -> str:
        loop = asyncio.get_running_loop()
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
        result = await loop.run_in_executor(None, crew.kickoff)
        return result.raw

    def _write_files(self, raw: str) -> None:
        raw = raw.replace("\r\n", "\n")
        for m in re.finditer(r"=== FILE: (.+?) ===\s*\n([\s\S]*?)(?=\n=== FILE:|\Z)", raw):
            self.ws.write_file(m.group(1).strip(), m.group(2).strip())

    async def _run_worker(self, worker_id: int, files: list, spec: str, timeout_seconds: float) -> str:
        file_paths = [f["path"] for f in files]
        await self.emit("generate", "worker_started", {"worker_id": worker_id, "files": file_paths})
        agent = make_file_writer(self._llm())
        task = build_generate_chunk_task(agent, files, spec)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
        loop = asyncio.get_running_loop()
        # wait_for cancels the asyncio Future but cannot stop the executor thread; the thread
        # runs to completion in the background. TimeoutError propagates to the caller normally.
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

        self.ws.write_text("_ors/generate.md", files_content)
        self.router.apply_pending()
        await self.emit("generate", "completed", {"file_tree": self.ws.file_tree()})

        # Review + Fix loop
        cached_review = self.ckpt.load(self.project_id, "review")
        if cached_review and cached_review.get("result") == "PASS":
            await self.emit("review", "completed", {"result": "PASS"})
            self._set_status("done")
            await self.emit("done", "done", {"workspace": f"workspace/{self.slug}"})
            return

        for i in range(MAX_FIX_ITERATIONS):
            await self.emit("review", "started", {"iteration": i + 1})
            reviewer = make_reviewer(self._llm())
            review = await self._run(build_review_task(reviewer, self.ws.file_tree(), files_content), reviewer)
            self.ws.write_json(f"_ors/review_{i + 1}.json", {"result": review})
            self.ws.append_text("_ors/run_log.txt", f"=== REVIEW {i + 1} — {self._ts()} ===\n{review}\n\n")

            if re.search(r'\bPASS\b', review):
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
            self._set_status("failed")
            await self.emit("review", "failed", {"message": f"Max fix iterations ({MAX_FIX_ITERATIONS}) reached without PASS"})
            return

        self._set_status("done")
        await self.emit("done", "done", {"workspace": f"workspace/{self.slug}"})
