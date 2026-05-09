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
  const res = await fetch(`${BASE}/${workspaceId}/sandbox/executions`);
  if (!res.ok) throw new Error("Failed to list sandbox executions");
  return res.json();
}

export async function executeSandbox(
  workspaceId: string,
  code: string,
  language: string,
): Promise<SandboxExecution> {
  const res = await fetch(`${BASE}/${workspaceId}/sandbox/executions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, language }),
  });
  if (!res.ok) throw new Error("Failed to execute sandbox code");
  return res.json();
}
