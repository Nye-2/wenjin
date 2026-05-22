import { authorizedFetch } from "@/lib/api/client";
import { readItemsArray } from "@/lib/api/v2/list-response";

const BASE = "/api/workspaces";

export type RunRecord = {
  id: string;
  workspace_id?: string;
  thread_id?: string | null;
  capability_id?: string | null;
  capability_name: string;
  status: "completed" | "failed_partial" | "failed" | "cancelled" | "running";
  started_at: string;
  completed_at?: string;
  summary: string;
  token_usage?: { input: number; output: number };
  progress?: number | null;
  primary_surface?: "prism" | "rooms" | "sandbox" | "none";
  review_items_count?: number;
  has_prism_changes?: boolean;
  failure_category?:
    | "launch_failed"
    | "queue_failed"
    | "node_failed"
    | "writeback_failed"
    | "commit_failed"
    | "unknown"
    | null;
  failure_message?: string | null;
};

export async function listRuns(
  workspaceId: string,
  query?: string,
): Promise<RunRecord[]> {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  const res = await authorizedFetch(
    `${BASE}/${workspaceId}/runs${params.toString() ? `?${params}` : ""}`,
  );
  if (!res.ok) throw new Error("Failed to list runs");
  const json = await res.json();
  return readItemsArray<RunRecord>(json, "runs");
}
