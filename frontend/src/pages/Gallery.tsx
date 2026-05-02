import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listProjects } from "../api/client";

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

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .finally(() => setLoading(false));
  }, []);

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
              <Link
                key={p.id}
                to={`/projects/${p.id}`}
                className="bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-gray-600 transition-colors group"
              >
                <div className="font-medium text-gray-100 group-hover:text-white transition-colors truncate">
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
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
