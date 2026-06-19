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
    throw new Error("文献资料格式异常");
  }
  const normalizedAuthors = readStringArray(value.authors);
  const authors =
    normalizedAuthors.length > 0
      ? normalizedAuthors
      : readStringArray(value.authors_json);
  const id = String(value.id ?? value.source_id ?? "");
  const addedBy = String(
    value.added_by ??
      value.source_label ??
      value.ingest_label ??
      value.source_type ??
      value.ingest_kind ??
      "library",
  );
  return {
    id,
    title: String(value.title ?? "未命名文献"),
    authors,
    year: typeof value.year === "number" ? value.year : undefined,
    doi: typeof value.doi === "string" ? value.doi : undefined,
    url: typeof value.url === "string" ? value.url : undefined,
    abstract: typeof value.abstract === "string" ? value.abstract : undefined,
    added_by: sourceLabel(addedBy),
    created_at: String(value.created_at ?? ""),
  };
}

function sourceLabel(value: string): string {
  const normalized = value.toLowerCase();
  if (normalized.startsWith("execution:") || normalized.includes("agent")) {
    return "研究团队";
  }
  if (normalized.includes("search") || normalized.includes("semantic")) {
    return "检索结果";
  }
  if (normalized.includes("upload") || normalized.includes("user")) {
    return "用户上传";
  }
  if (normalized === "library" || normalized === "source") {
    return "资料库";
  }
  return value;
}

function normalizeLibraryDetail(value: unknown): LibraryItemDetail {
  const base = normalizeLibraryItem(value);
  const record = value as Record<string, unknown>;
  return {
    ...base,
    venue: typeof record.venue === "string" ? record.venue : undefined,
    source: sourceLabel(
      typeof record.source === "string"
        ? record.source
        : typeof record.source_type === "string"
          ? record.source_type
          : "library",
    ),
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
  if (!res.ok) throw new Error("文献资料加载失败");
  const json = await res.json();
  return readItemsArray<unknown>(json, "文献资料").map(normalizeLibraryItem);
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
  if (!res.ok) throw new Error("文献资料删除失败");
}

export async function getLibraryItem(
  workspaceId: string,
  itemId: string,
): Promise<LibraryItemDetail> {
  const res = await authorizedFetch(`${BASE}/${workspaceId}/library/${itemId}`);
  if (!res.ok) {
    throw new Error("文献详情加载失败");
  }
  return normalizeLibraryDetail(await res.json());
}
