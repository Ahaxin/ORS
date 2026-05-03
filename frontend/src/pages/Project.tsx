import { useParams, Link, useNavigate } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { getProject, deleteProject, getLMStudioStatus, resumeProject } from "../api/client";
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

type LMStatus = { model: string | null; status: "ready" | "unavailable" };

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const projectId = Number(id);
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [lmStatus, setLmStatus] = useState<LMStatus | null>(null);
  const [resuming, setResuming] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const lmIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const events = useSSE(projectId);

  useEffect(() => {
    getProject(projectId).then(setProject);
  }, [projectId]);

  useEffect(() => {
    const last = events.filter(isStepEvent).at(-1);
    if (last?.type === "done") {
      getProject(projectId).then(setProject);
    }
  }, [events, projectId]);

  const stepEvents = events.filter(isStepEvent);
  const activeTask = [...stepEvents].reverse().find((e) => e.type === "started")?.task ?? "";
  const isDone = stepEvents.some((e) => e.type === "done");

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
    } catch (e: unknown) {
      setDeleteError(e instanceof Error ? e.message : "Delete failed");
      setConfirmDelete(false);
    }
  };

  const handleResume = async () => {
    if (!project) return;
    setResuming(true);
    setResumeError(null);
    try {
      const data = await resumeProject(project.id);
      setProject(p => p ? { ...p, status: data.status } : p);
    } catch (e: unknown) {
      setResumeError(e instanceof Error ? e.message : "Resume failed");
    } finally {
      setResuming(false);
    }
  };

  if (!project) {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <span className="text-gray-500">Loading…</span>
      </div>
    );
  }

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
          {(project.status === "stalled" || project.status === "paused") && (
            <>
              {resumeError && <span className="text-xs text-red-400">{resumeError}</span>}
              <button
                onClick={handleResume}
                disabled={resuming}
                className="text-xs bg-orange-600 hover:bg-orange-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium px-2 py-1 rounded transition-colors"
              >
                {resuming ? "Resuming…" : "Resume"}
              </button>
            </>
          )}
          <span
            className={`text-sm ${
              isDone
                ? "text-blue-400"
                : project.status === "failed"
                ? "text-red-400"
                : project.status === "stalled"
                ? "text-orange-400"
                : project.status === "paused"
                ? "text-yellow-400"
                : "text-green-400"
            }`}
          >
            {isDone
              ? "✓ Done"
              : project.status === "failed"
              ? "✗ Failed"
              : project.status === "stalled"
              ? "⚠ Stalled"
              : project.status === "paused"
              ? "⏸ Paused"
              : "● Running"}
          </span>

          {/* Delete */}
          {deleteError && <span className="text-xs text-red-400">{deleteError}</span>}
          {confirmDelete ? (
            <div className="flex items-center gap-1 text-xs">
              <span className="text-gray-300">Delete?</span>
              <button onClick={handleDelete} className="text-red-400 hover:text-red-300 font-medium">Yes</button>
              <button onClick={() => { setConfirmDelete(false); setDeleteError(null); }} className="text-gray-400 hover:text-gray-200">No</button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              disabled={!isDone && project.status === "running"}
              className="text-gray-500 hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed text-sm font-bold transition-colors"
              title={!isDone && project.status === "running" ? "Can't delete a running project" : "Delete project"}
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

      {/* Done/stalled/paused/failed banner */}
      {(isDone || project.status === "stalled" || project.status === "paused" || project.status === "failed") && (
        <div className="px-6 pb-4 shrink-0">
          <div className={`border rounded-lg px-4 py-3 text-sm ${
            isDone
              ? "bg-green-950 border-green-700 text-green-300"
              : project.status === "stalled"
              ? "bg-orange-950 border-orange-700 text-orange-300"
              : project.status === "paused"
              ? "bg-yellow-950 border-yellow-700 text-yellow-300"
              : "bg-red-950 border-red-700 text-red-300"
          }`}>
            {isDone
              ? <>✓ Build complete — files written to <code className="text-green-200">workspace/{project.slug}/</code></>
              : project.status === "stalled"
              ? "⚠ Run stalled (LM Studio timed out). Click Resume to continue from last checkpoint."
              : project.status === "paused"
              ? "⏸ Run paused for review. Click Resume to continue."
              : "✗ Run failed."}
            <span className="ml-4 space-x-3">
              <a
                href={`http://localhost:8000/workspace/${project.slug}/_ors/run_log.txt`}
                target="_blank"
                rel="noreferrer"
                className="underline opacity-70 hover:opacity-100"
              >
                View run log
              </a>
              <a
                href={`http://localhost:8000/workspace/${project.slug}/_ors/generate_log.txt`}
                target="_blank"
                rel="noreferrer"
                className="underline opacity-70 hover:opacity-100"
              >
                View generate log
              </a>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
