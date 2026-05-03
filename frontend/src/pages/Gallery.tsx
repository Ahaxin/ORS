import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { listProjects, deleteProject } from "../api/client";

type ProjectSummary = {
  id: number;
  slug: string;
  status: string;
  active_model: string;
};

const STATUS_COLOR: Record<string, string> = {
  running: "text-green-400",
  done: "text-blue-400",
  failed: "text-red-400",
  pending: "text-gray-400",
};

export default function Gallery() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<Record<number, string>>({});
  const fetchingRef = useRef(false);

  const fetchProjects = async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      const data = await listProjects();
      setProjects(data);
    } catch (e) {
      console.error("Failed to fetch projects", e);
    } finally {
      fetchingRef.current = false;
    }
  };

  useEffect(() => {
    fetchProjects().finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const hasRunning = projects.some(p => p.status === "running");
    if (!hasRunning) return;
    const id = setInterval(fetchProjects, 10_000);
    return () => clearInterval(id);
  }, [projects]);

  const handleDelete = async (id: number) => {
    try {
      await deleteProject(id);
      setProjects(prev => prev.filter(p => p.id !== id));
      setDeleteError(prev => { const next = { ...prev }; delete next[id]; return next; });
      setConfirmId(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Delete failed";
      setDeleteError(prev => ({ ...prev, [id]: msg }));
      setConfirmId(null);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-2xl font-bold text-yellow-400">⚡ ORS</h1>
          <Link
            to="/new"
            className="bg-yellow-500 text-black font-bold px-4 py-2 rounded-lg hover:bg-yellow-400 transition-colors"
          >
            + New Project
          </Link>
        </div>

        {loading ? (
          <p className="text-gray-500">Loading…</p>
        ) : projects.length === 0 ? (
          <div className="text-center py-24 space-y-3">
            <p className="text-gray-500 text-lg">No projects yet.</p>
            <Link to="/new" className="text-yellow-400 hover:text-yellow-300 transition-colors">
              Build your first app →
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((p) => (
              <div key={p.id} className="relative group">
                <Link
                  to={`/projects/${p.id}`}
                  className="block bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-gray-600 transition-colors"
                >
                  <div className="font-medium text-gray-100 group-hover:text-white transition-colors truncate pr-6">
                    {p.slug}
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <span className={`text-xs ${STATUS_COLOR[p.status] ?? "text-gray-400"}`}>
                      {p.status}
                    </span>
                    <span className="text-gray-700">·</span>
                    <span className="text-xs text-gray-500">{p.active_model}</span>
                  </div>
                </Link>
                {deleteError[p.id] && (
                  <p className="text-xs text-red-400 mt-1 px-4">{deleteError[p.id]}</p>
                )}

                {/* Delete button — visible on hover, disabled for running projects */}
                {confirmId === p.id ? (
                  <div className="absolute top-2 right-2 flex items-center gap-1 bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-xs z-10">
                    <span className="text-gray-300">Delete?</span>
                    <button
                      onClick={(e) => { e.preventDefault(); handleDelete(p.id); }}
                      className="text-red-400 hover:text-red-300 font-medium"
                    >Yes</button>
                    <button
                      onClick={(e) => { e.preventDefault(); setConfirmId(null); }}
                      className="text-gray-400 hover:text-gray-200"
                    >No</button>
                  </div>
                ) : (
                  <button
                    onClick={(e) => { e.preventDefault(); setConfirmId(p.id); }}
                    disabled={p.status === "running"}
                    className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 disabled:opacity-20 disabled:cursor-not-allowed transition-opacity text-sm font-bold"
                    title={p.status === "running" ? "Can't delete a running project" : "Delete project"}
                  >×</button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
