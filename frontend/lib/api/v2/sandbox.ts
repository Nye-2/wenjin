import { authorizedFetch } from "@/lib/api/client";

const BASE = "/api/workspaces";

export type SandboxExecution = {
  id: string;
  code: string;
  language: string;
  output: string;
  status: "completed" | "failed";
  created_at: string;
};

export async function listSandboxExecutions(
  workspaceId: string,
): Promise<SandboxExecution[]> {
  // Backend has no list endpoint; return empty until added
  void workspaceId;
  return [];
}

export async function executeSandbox(
  workspaceId: string,
  code: string,
  language: string,
): Promise<SandboxExecution> {
  const res = await authorizedFetch(`${BASE}/${workspaceId}/sandbox/exec`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command: code, timeout_seconds: 30 }),
  });
  if (!res.ok) throw new Error("Failed to execute sandbox code");
  const json = await res.json();
  return {
    id: json.sandbox_id ?? crypto.randomUUID(),
    code,
    language,
    output: json.output ?? json.note ?? "",
    status: json.status === "queued" ? "completed" : "failed",
    created_at: new Date().toISOString(),
  };
}
