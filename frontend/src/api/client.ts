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
