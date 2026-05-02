import { switchModel } from "../api/client";

const MODELS = ["lmstudio", "openai", "anthropic", "gemini"];

type Props = { projectId: number; activeModel: string; pendingModel?: string };

export default function ModelPicker({ projectId, activeModel, pendingModel }: Props) {
  return (
    <select
      className="bg-gray-800 text-blue-300 border border-gray-600 rounded-full px-3 py-1 text-sm cursor-pointer"
      value={pendingModel || activeModel}
      onChange={e => switchModel(projectId, e.target.value)}
    >
      {MODELS.map(m => <option key={m} value={m}>{m}</option>)}
    </select>
  );
}
