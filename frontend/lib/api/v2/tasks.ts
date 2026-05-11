import { authorizedFetch } from "@/lib/api/client";

const BASE = "/api/workspaces";

export type WorkspaceTask = {
  id: string;
  title: string;
  description?: string;
  status: "pending" | "in_progress" | "completed" | "cancelled";
  priority?: number;
  created_at: string;
};

export async function listTasks(
  workspaceId: string,
  query?: string,
): Promise<WorkspaceTask[]> {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  const res = await authorizedFetch(`${BASE}/${workspaceId}/tasks${params.toString() ? `?${params}` : ""}`);
  if (!res.ok) throw new Error("Failed to list tasks");
  const json = await res.json();
  return json.items ?? json;
}

export async function createTask(
  workspaceId: string,
  title: string,
  description?: string,
): Promise<WorkspaceTask> {
  const res = await authorizedFetch(`${BASE}/${workspaceId}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, description }),
  });
  if (!res.ok) throw new Error("Failed to create task");
  return res.json();
}

export async function deleteTask(
  workspaceId: string,
  taskId: string,
): Promise<void> {
  const res = await authorizedFetch(`${BASE}/${workspaceId}/tasks/${taskId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete task");
}

export async function updateTaskStatus(
  workspaceId: string,
  taskId: string,
  status: string,
): Promise<void> {
  const res = await authorizedFetch(`${BASE}/${workspaceId}/tasks/${taskId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error("Failed to update task status");
}
