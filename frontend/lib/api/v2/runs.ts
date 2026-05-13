import { authorizedFetch } from "@/lib/api/client";

const BASE = "/api/workspaces";

export type RunRecord = {
  id: string;
  capability_name: string;
  status: "completed" | "failed_partial" | "failed" | "cancelled" | "running";
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
  const res = await authorizedFetch(`${BASE}/${workspaceId}/runs${params.toString() ? `?${params}` : ""}`);
  if (!res.ok) throw new Error("Failed to list runs");
  const json = await res.json();
  return json.items ?? json;
}
