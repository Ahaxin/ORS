import { useEffect, useState } from "react";

export type StepEvent = {
  task: string;
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

export function useSSE(projectId: number | null) {
  const [events, setEvents] = useState<TaskEvent[]>([]);

  useEffect(() => {
    if (!projectId) return;
    const es = new EventSource(`http://localhost:8000/projects/${projectId}/stream`);
    es.onmessage = (e) => setEvents(prev => [...prev, JSON.parse(e.data) as TaskEvent]);
    es.onerror = () => es.close();
    return () => es.close();
  }, [projectId]);

  return events;
}
