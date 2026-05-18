import { authorizedFetch } from "@/lib/api/client";
import { readItemsArray } from "@/lib/api/v2/list-response";

const BASE = "/api/workspaces";

export type MemoryFact = {
  id: string;
  content: string;
  category: string;
  confidence: number;
  created_at: string;
};

export async function listMemoryFacts(
  workspaceId: string,
  query?: string,
): Promise<MemoryFact[]> {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  const res = await authorizedFetch(
    `${BASE}/${workspaceId}/memory${params.toString() ? `?${params}` : ""}`,
  );
  if (!res.ok) throw new Error("Failed to list memory facts");
  const json = await res.json();
  return readItemsArray<MemoryFact>(json, "memory facts");
}

export async function deleteMemoryFact(
  workspaceId: string,
  factId: string,
): Promise<void> {
  const res = await authorizedFetch(`${BASE}/${workspaceId}/memory/${factId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete memory fact");
}
