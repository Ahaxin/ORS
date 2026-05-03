import { useState } from "react";
import { isStepEvent } from "../hooks/useSSE";
import type { TaskEvent } from "../hooks/useSSE";

type Props = { events: TaskEvent[]; activeTask: string };

export default function LogViewer({ events, activeTask }: Props) {
  const [expanded, setExpanded] = useState<string[]>([activeTask]);

  const byTask = events.reduce((acc, e) => {
    (acc[e.task] ??= []).push(e);
    return acc;
  }, {} as Record<string, TaskEvent[]>);

  const toggle = (task: string) =>
    setExpanded(prev => prev.includes(task) ? prev.filter(t => t !== task) : [...prev, task]);

  return (
    <div className="flex flex-col gap-2 flex-1 overflow-hidden">
      {Object.entries(byTask).map(([task, evts]) => (
        <div key={task} className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <button onClick={() => toggle(task)}
            className="w-full text-left px-4 py-2 text-xs text-gray-400 flex justify-between hover:bg-gray-800">
            <span>{expanded.includes(task) ? "▼" : "▶"} {task} ({evts.length} events)</span>
          </button>
          {expanded.includes(task) && (
            <div className="font-mono text-xs text-gray-300 p-4 max-h-64 overflow-y-auto">
              {evts.map((e, i) => (
                <div key={i}>
                  <span className="text-gray-500">[{e.type}]</span>{" "}
                  {isStepEvent(e)
                    ? (e.output ? e.output.slice(0, 300) : e.issues ?? e.message ?? "")
                    : `[worker ${e.worker_id}] ${e.files.join(", ")}`}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
