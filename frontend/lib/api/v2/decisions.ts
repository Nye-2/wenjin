import { authorizedFetch } from "@/lib/api/client";
import { readItemsArray } from "@/lib/api/v2/list-response";

const BASE = "/api/workspaces";

export type Decision = {
  id: string;
  key: string;
  value: string;
  confidence: number;
  rationale?: string;
  created_at: string;
};

export async function listDecisions(
  workspaceId: string,
  query?: string,
): Promise<Decision[]> {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  const res = await authorizedFetch(
    `${BASE}/${workspaceId}/decisions${params.toString() ? `?${params}` : ""}`,
  );
  if (!res.ok) throw new Error("Failed to list decisions");
  const json = await res.json();
  return readItemsArray<Decision>(json, "decisions");
}
