import { useEffect, useState } from "react";
import { getProjectEvents } from "../api/client";

export type StepEvent = {
  task: "clarify" | "architect" | "generate" | "review" | "fix" | "done";
  type: "started" | "completed" | "paused" | "failed" | "done";
  output?: string;
  issues?: string;
  file_tree?: string;
  iteration?: number;
  result?: string;
  workspace?: string;
  message?: string;
};

export type WorkerEvent = {
  task: "generate";
  type: "worker_started" | "worker_completed";
  worker_id: number;
  files: string[];
};

export type TaskEvent = StepEvent | WorkerEvent;

export const isStepEvent = (e: TaskEvent): e is StepEvent =>
  e.type !== "worker_started" && e.type !== "worker_completed";

export const isWorkerEvent = (e: TaskEvent): e is WorkerEvent =>
  e.type === "worker_started" || e.type === "worker_completed";

export function useSSE(projectId: number | null) {
  const [events, setEvents] = useState<TaskEvent[]>([]);

  useEffect(() => {
    if (!projectId) return;
    setEvents([]);
    getProjectEvents(projectId)
      .then((history) => setEvents(Array.isArray(history) ? history as TaskEvent[] : []))
      .catch(() => setEvents([]));

    const es = new EventSource(`http://localhost:8000/projects/${projectId}/stream`);
    es.onmessage = (e) => setEvents(prev => [...prev, JSON.parse(e.data) as TaskEvent]);
    es.onerror = () => es.close();
    return () => es.close();
  }, [projectId]);

  return events;
}
