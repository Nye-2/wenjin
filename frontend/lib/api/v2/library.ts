import { authorizedFetch } from "@/lib/api/client";
import { readItemsArray } from "@/lib/api/v2/list-response";

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

export type LibraryItemDetail = LibraryItem & {
  venue?: string;
  abstract?: string;
  source?: string;
};

export async function listLibraryItems(
  workspaceId: string,
  query?: string,
): Promise<LibraryItem[]> {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  const res = await authorizedFetch(
    `${BASE}/${workspaceId}/library${params.toString() ? `?${params}` : ""}`,
  );
  if (!res.ok) throw new Error("Failed to list library items");
  const json = await res.json();
  return readItemsArray<LibraryItem>(json, "library items");
}

export async function deleteLibraryItem(
  workspaceId: string,
  itemId: string,
): Promise<void> {
  const res = await authorizedFetch(
    `${BASE}/${workspaceId}/library/${itemId}`,
    {
      method: "DELETE",
    },
  );
  if (!res.ok) throw new Error("Failed to delete library item");
}

export async function getLibraryItem(
  workspaceId: string,
  itemId: string,
): Promise<LibraryItemDetail> {
  const res = await authorizedFetch(`${BASE}/${workspaceId}/library/${itemId}`);
  if (!res.ok) {
    throw new Error("Failed to load library item");
  }
  return (await res.json()) as LibraryItemDetail;
}
