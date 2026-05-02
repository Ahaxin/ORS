import type { TaskEvent } from "../hooks/useSSE";

const TASKS = ["clarify", "architect", "generate", "review", "fix"];

type Props = { events: TaskEvent[]; activeModel: string; pendingModel?: string };

export default function TaskBoard({ events, activeModel, pendingModel }: Props) {
  const statusOf = (task: string) => {
    const last = [...events].reverse().find(e => e.task === task);
    if (!last) return "pending";
    if (last.type === "completed" || last.type === "done") return "done";
    if (last.type === "paused") return "paused";
    if (last.type === "failed") return "failed";
    return "running";
  };

  const colors: Record<string, string> = {
    done: "text-green-400 border-green-800 bg-green-950",
    running: "text-yellow-300 border-blue-700 bg-blue-950",
    paused: "text-orange-400 border-orange-700 bg-orange-950",
    failed: "text-red-400 border-red-800 bg-red-950",
    pending: "text-gray-600 border-gray-800 bg-gray-950",
  };

  return (
    <div className="flex flex-col gap-2 w-64 shrink-0">
      {TASKS.map(task => {
        const status = statusOf(task);
        return (
          <div key={task} className={`border rounded-lg p-3 ${colors[status]}`}>
            <div className="font-medium capitalize">{task}</div>
            <div className="text-xs opacity-60">{activeModel}{status === "running" ? " · running…" : ""}</div>
          </div>
        );
      })}
      {pendingModel && (
        <div className="text-xs text-yellow-400 mt-1">⚑ Switching to {pendingModel} at next task</div>
      )}
    </div>
  );
}
