import { authorizedFetch } from "@/lib/api/client";

const BASE = "/api/workspaces";

export type LibraryItem = {
  id: string;
  title: string;
  authors: string[];
  year?: number;
  doi?: string;
  url?: string;
  abstract?: string;
  added_by: string;
  created_at: string;
};

export async function listLibraryItems(
  workspaceId: string,
  query?: string,
): Promise<LibraryItem[]> {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  const res = await authorizedFetch(`${BASE}/${workspaceId}/library${params.toString() ? `?${params}` : ""}`);
  if (!res.ok) throw new Error("Failed to list library items");
  const json = await res.json();
  return json.items ?? json;
}

export async function deleteLibraryItem(
  workspaceId: string,
  itemId: string,
): Promise<void> {
  const res = await authorizedFetch(`${BASE}/${workspaceId}/library/${itemId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete library item");
}
