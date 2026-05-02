import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createProject } from "../api/client";

export default function NewProject() {
  const [spec, setSpec] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async () => {
    if (!spec.trim() || loading) return;
    setLoading(true);
    try {
      const project = await createProject(spec);
      navigate(`/projects/${project.id}`);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleSubmit();
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
      <div className="w-full max-w-xl space-y-4 p-8">
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-2xl font-bold text-yellow-400">⚡ ORS</h1>
          <button
            onClick={() => navigate("/")}
            className="text-gray-500 hover:text-gray-300 text-sm transition-colors"
          >
            ← Projects
          </button>
        </div>
        <p className="text-gray-400">Describe what you want to build</p>
        <textarea
          className="w-full bg-gray-900 border border-gray-700 rounded-lg p-4 text-gray-100 min-h-36 resize-none focus:outline-none focus:border-gray-500 transition-colors"
          placeholder="Build me a reservation dashboard for a restaurant with calendar view and booking form..."
          value={spec}
          onChange={(e) => setSpec(e.target.value)}
          onKeyDown={handleKeyDown}
          autoFocus
        />
        <div className="flex items-center justify-between">
          <span className="text-gray-600 text-xs">Ctrl+Enter to submit</span>
          <button
            onClick={handleSubmit}
            disabled={!spec.trim() || loading}
            className="bg-yellow-500 text-black font-bold px-6 py-2 rounded-lg hover:bg-yellow-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? "Starting…" : "Build →"}
          </button>
        </div>
      </div>
    </div>
  );
}
