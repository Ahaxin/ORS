import asyncio
import json
import re
from crewai import Crew, Process
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

    async def _run(self, task, agent) -> str:
        loop = asyncio.get_running_loop()
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
        result = await loop.run_in_executor(None, crew.kickoff)
        return result.raw

    def _write_files(self, raw: str):
        raw = raw.replace("\r\n", "\n")
        for m in re.finditer(r"=== FILE: (.+?) ===\s*\n([\s\S]*?)(?=\n=== FILE:|\Z)", raw):
            self.ws.write_file(m.group(1).strip(), m.group(2).strip())

    async def _run_worker(self, worker_id: int, files: list, spec: str) -> str:
        await self.emit("generate", "worker_started", {
            "worker_id": worker_id,
            "files": [f["path"] for f in files],
        })
        agent = make_file_writer(self._llm())
        task = build_generate_chunk_task(agent, files, spec)
        crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True)
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, crew.kickoff)
        await self.emit("generate", "worker_completed", {
            "worker_id": worker_id,
            "files": [f["path"] for f in files],
        })
        return result.raw

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
        self.router.apply_pending()
        await self.emit("architect", "completed", {"output": plan})

        # Generate
        await self.emit("generate", "started")
        cached = self.ckpt.load(self.project_id, "generate")
        if cached:
            files_content = cached["files_content"]
            self._write_files(files_content)  # re-populate workspace after restart
        else:
            try:
                plan_data = json.loads(plan)
                file_list = plan_data["files"]
            except (json.JSONDecodeError, KeyError, TypeError):
                file_list = None

            if file_list:
                concurrency = self.router.get_provider().concurrency
                n = min(concurrency, len(file_list))  # n <= len ensures no empty chunks
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
        self.router.apply_pending()
        await self.emit("generate", "completed", {"file_tree": self.ws.file_tree()})

        # Review + Fix loop
        for i in range(MAX_FIX_ITERATIONS):
            await self.emit("review", "started", {"iteration": i + 1})
            reviewer = make_reviewer(self._llm())
            review = await self._run(build_review_task(reviewer, self.ws.file_tree(), files_content), reviewer)
            self.ws.write_json(f"_ors/review_{i + 1}.json", {"result": review})

            if "PASS" in review:
                self.ckpt.save(self.project_id, "review", self.router.active_model, {"result": "PASS"})
                await self.emit("review", "completed", {"result": "PASS"})
                self.router.apply_pending()
                break

            if not self.router.should_auto_retry():
                self.router.apply_pending()
                await self.emit("review", "paused", {"issues": review})
                return

            await self.emit("fix", "started", {"iteration": i + 1})
            fixer = make_fixer(self._llm())
            files_content = await self._run(build_fix_task(fixer, review, files_content), fixer)
            self._write_files(files_content)
            self.ws.write_text(f"_ors/fix_{i + 1}.md", files_content)
            self.router.apply_pending()
            await self.emit("fix", "completed")
        else:
            # Loop completed without break = no PASS achieved
            await self.emit("review", "failed", {"message": f"Max fix iterations ({MAX_FIX_ITERATIONS}) reached without PASS"})

        await self.emit("done", "done", {"workspace": f"workspace/{self.slug}"})
