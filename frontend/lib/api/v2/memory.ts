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
  const res = await fetch(
    `${BASE}/${workspaceId}/memory${params.toString() ? `?${params}` : ""}`,
  );
  if (!res.ok) throw new Error("Failed to list memory facts");
  return res.json();
}

export async function deleteMemoryFact(
  workspaceId: string,
  factId: string,
): Promise<void> {
  const res = await fetch(`${BASE}/${workspaceId}/memory/${factId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete memory fact");
}
