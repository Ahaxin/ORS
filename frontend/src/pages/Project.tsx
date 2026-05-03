import { useParams, Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { getProject } from "../api/client";
import { useSSE, isStepEvent } from "../hooks/useSSE";
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

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = Number(id);
  const [project, setProject] = useState<Project | null>(null);
  const events = useSSE(projectId);

  useEffect(() => {
    getProject(projectId).then(setProject);
  }, [projectId]);

  useEffect(() => {
    const last = events.filter(isStepEvent).at(-1);
    if (last?.type === "completed" || last?.type === "done") {
      getProject(projectId).then(setProject);
    }
  }, [events]);

  if (!project) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <span className="text-gray-500">Loading…</span>
      </div>
    );
  }

  const stepEvents = events.filter(isStepEvent);
  const activeTask = [...stepEvents].reverse().find((e) => e.type === "started")?.task ?? "";
  const isDone = stepEvents.some((e) => e.type === "done");

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
