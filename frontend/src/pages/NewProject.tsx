import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createProject } from "../api/client";

const MODELS = [
  { value: "lmstudio",  label: "LM Studio (local)" },
  { value: "openai",    label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "gemini",    label: "Gemini" },
];

export default function NewProject() {
  const [spec, setSpec] = useState("");
  const [model, setModel] = useState("lmstudio");
  const [loading, setLoading] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (ev) => setSpec((ev.target?.result as string) ?? "");
    reader.readAsText(file);
    e.target.value = "";
  };

  const handleSubmit = async () => {
    if (!spec.trim() || loading) return;
    setLoading(true);
    try {
      const project = await createProject(spec, model);
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
        {/* Header */}
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

        {/* Spec textarea */}
        <div className="relative">
          <textarea
            className="w-full bg-gray-900 border border-gray-700 rounded-lg p-4 text-gray-100 min-h-40 resize-none focus:outline-none focus:border-gray-500 transition-colors"
            placeholder="Build me a reservation dashboard for a restaurant with calendar view and booking form..."
            value={spec}
            onChange={(e) => setSpec(e.target.value)}
            onKeyDown={handleKeyDown}
            autoFocus
          />
          {fileName && (
            <div className="absolute top-2 right-2 flex items-center gap-1 bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-xs text-gray-300">
              <span>📄</span>
              <span className="max-w-36 truncate">{fileName}</span>
              <button
                onClick={() => { setFileName(null); setSpec(""); }}
                className="ml-1 text-gray-500 hover:text-gray-200"
                title="Clear file"
              >
                ×
              </button>
            </div>
          )}
        </div>

        {/* Controls row */}
        <div className="flex items-center gap-3">
          {/* File upload */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.yaml,.yml,.json"
            onChange={handleFile}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 bg-gray-800 border border-gray-700 hover:border-gray-500 text-gray-300 hover:text-white text-sm px-3 py-2 rounded-lg transition-colors"
            title="Upload a spec file (.txt, .md, .yaml)"
          >
            <span>↑</span> Upload spec
          </button>

          {/* Model picker */}
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="flex-1 bg-gray-800 border border-gray-700 hover:border-gray-500 text-gray-300 text-sm px-3 py-2 rounded-lg cursor-pointer focus:outline-none transition-colors"
          >
            {MODELS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={!spec.trim() || loading}
            className="bg-yellow-500 text-black font-bold px-5 py-2 rounded-lg hover:bg-yellow-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
          >
            {loading ? "Starting…" : "Build →"}
          </button>
        </div>

        <p className="text-gray-700 text-xs">Ctrl+Enter to submit</p>
      </div>
    </div>
  );
}
