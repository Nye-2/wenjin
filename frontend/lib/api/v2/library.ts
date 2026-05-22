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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function normalizeLibraryItem(value: unknown): LibraryItem {
  if (!isRecord(value)) {
    throw new Error("Invalid library item response");
  }
  const normalizedAuthors = readStringArray(value.authors);
  const authors =
    normalizedAuthors.length > 0
      ? normalizedAuthors
      : readStringArray(value.authors_json);
  const id = String(value.id ?? value.source_id ?? "");
  return {
    id,
    title: String(value.title ?? "Untitled reference"),
    authors,
    year: typeof value.year === "number" ? value.year : undefined,
    doi: typeof value.doi === "string" ? value.doi : undefined,
    url: typeof value.url === "string" ? value.url : undefined,
    abstract: typeof value.abstract === "string" ? value.abstract : undefined,
    added_by: String(
      value.added_by ??
        value.source_label ??
        value.ingest_label ??
        value.source_type ??
        value.ingest_kind ??
        "library",
    ),
    created_at: String(value.created_at ?? ""),
  };
}

function normalizeLibraryDetail(value: unknown): LibraryItemDetail {
  const base = normalizeLibraryItem(value);
  const record = value as Record<string, unknown>;
  return {
    ...base,
    venue: typeof record.venue === "string" ? record.venue : undefined,
    source: typeof record.source === "string"
      ? record.source
      : typeof record.source_type === "string"
        ? record.source_type
        : undefined,
  };
}

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
  return readItemsArray<unknown>(json, "library items").map(normalizeLibraryItem);
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
  return normalizeLibraryDetail(await res.json());
}
