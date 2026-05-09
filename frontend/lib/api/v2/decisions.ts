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
  const res = await fetch(
    `${BASE}/${workspaceId}/decisions${params.toString() ? `?${params}` : ""}`,
  );
  if (!res.ok) throw new Error("Failed to list decisions");
  return res.json();
}
