import type { TaskEvent, StepEvent, WorkerEvent } from "../hooks/useSSE";

const TASKS = ["clarify", "architect", "generate", "review", "fix"];

type Props = { events: TaskEvent[]; activeModel: string; pendingModel?: string };

const isStepEvent = (e: TaskEvent): e is StepEvent =>
  e.type !== "worker_started" && e.type !== "worker_completed";

const isWorkerEvent = (e: TaskEvent): e is WorkerEvent =>
  e.type === "worker_started" || e.type === "worker_completed";

export default function TaskBoard({ events, activeModel, pendingModel }: Props) {
  const stepEvents = events.filter(isStepEvent);
  const workerEvents = events.filter(isWorkerEvent);

  const statusOf = (task: string) => {
    const last = [...stepEvents].reverse().find(e => e.task === task);
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

  // Build worker status map: { workerId -> "running" | "done" }
  const workerStatus = new Map<number, "running" | "done">();
  for (const e of workerEvents) {
    workerStatus.set(e.worker_id, e.type === "worker_completed" ? "done" : "running");
  }
  const workerFileMap = new Map<number, string[]>();
  for (const e of workerEvents) {
    if (!workerFileMap.has(e.worker_id)) workerFileMap.set(e.worker_id, e.files);
  }

  const generateStatus = statusOf("generate");
  const allWorkersDone = workerStatus.size > 0 && [...workerStatus.values()].every(s => s === "done");
  const showWorkers = generateStatus === "running" || (workerStatus.size > 0 && !allWorkersDone);

  return (
    <div className="flex flex-col gap-2 w-64 shrink-0">
      {TASKS.map(task => {
        const status = statusOf(task);
        return (
          <div key={task}>
            <div className={`border rounded-lg p-3 ${colors[status]}`}>
              <div className="font-medium capitalize">{task}</div>
              <div className="text-xs opacity-60">
                {activeModel}{status === "running" ? " · running…" : ""}
              </div>
            </div>
            {task === "generate" && showWorkers && (
              <div className="ml-3 mt-1 flex flex-col gap-1">
                {[...workerFileMap.entries()].map(([id, files]) => {
                  const ws = workerStatus.get(id) ?? "running";
                  return (
                    <div key={id} className={`text-xs px-2 py-1 rounded border ${
                      ws === "done"
                        ? "border-green-900 bg-green-950 text-green-400"
                        : "border-blue-900 bg-blue-950 text-blue-300"
                    }`}>
                      <span className="font-medium">Worker {id + 1}:</span>{" "}
                      {files.slice(0, 3).join(", ")}{files.length > 3 ? ` +${files.length - 3}` : ""}{" "}
                      <span className="opacity-60">{ws === "done" ? "● done" : "● running"}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
      {pendingModel && (
        <div className="text-xs text-yellow-400 mt-1">⚑ Switching to {pendingModel} at next task</div>
      )}
    </div>
  );
}
