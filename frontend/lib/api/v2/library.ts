const BASE = "/api/workspaces";

export type LibraryItem = {
  id: string;
  title: string;
  authors: string[];
  year?: number;
  doi?: string;
  url?: string;
  abstract?: string;
  source: "user_upload" | "search_result" | "ai_suggested";
  created_at: string;
};

export async function listLibraryItems(
  workspaceId: string,
  query?: string,
): Promise<LibraryItem[]> {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  const res = await fetch(`${BASE}/${workspaceId}/library${params.toString() ? `?${params}` : ""}`);
  if (!res.ok) throw new Error("Failed to list library items");
  return res.json();
}

export async function deleteLibraryItem(
  workspaceId: string,
  itemId: string,
): Promise<void> {
  const res = await fetch(`${BASE}/${workspaceId}/library/${itemId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete library item");
}
