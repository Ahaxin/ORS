const BASE = "http://localhost:8000";

export async function createProject(spec: string, model?: string) {
  const res = await fetch(`${BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ spec, model }),
  });
  return res.json();
}

export const listProjects = () => fetch(`${BASE}/projects`).then(r => r.json());

export const getProject = (id: number) => fetch(`${BASE}/projects/${id}`).then(r => r.json());

export async function switchModel(projectId: number, model: string) {
  return fetch(`${BASE}/projects/${projectId}/model`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  }).then(r => r.json());
}

export async function deleteProject(id: number): Promise<void> {
  const res = await fetch(`${BASE}/projects/${id}`, { method: "DELETE" });
  if (res.status === 409) throw new Error("Cannot delete a running project");
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}

export async function getLMStudioStatus(): Promise<{ model: string | null; status: "ready" | "unavailable" }> {
  return fetch(`${BASE}/providers/lmstudio/status`).then(r => r.json());
}

export async function resumeProject(id: number): Promise<{ id: number; status: string }> {
  const res = await fetch(`${BASE}/projects/${id}/resume`, { method: "POST" });
  if (res.status === 409) {
    const data = await res.json();
    throw new Error(data.detail ?? "Cannot resume project");
  }
  if (!res.ok) throw new Error(`Resume failed: ${res.status}`);
  return res.json();
}
