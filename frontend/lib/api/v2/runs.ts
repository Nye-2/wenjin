const BASE = "/api/workspaces";

export type RunRecord = {
  id: string;
  capability_name: string;
  status: "completed" | "failed" | "cancelled" | "running";
  started_at: string;
  completed_at?: string;
  summary: string;
  token_usage?: { input: number; output: number };
};

export async function listRuns(
  workspaceId: string,
  query?: string,
): Promise<RunRecord[]> {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  const res = await fetch(`${BASE}/${workspaceId}/runs${params.toString() ? `?${params}` : ""}`);
  if (!res.ok) throw new Error("Failed to list runs");
  return res.json();
}
