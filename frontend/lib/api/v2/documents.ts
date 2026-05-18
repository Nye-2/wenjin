import { authorizedFetch } from "@/lib/api/client";
import { readItemsArray } from "@/lib/api/v2/list-response";

const BASE = "/api/workspaces";

export type Document = {
  id: string;
  name: string;
  mime_type: string;
  doc_kind: "draft" | "outline" | "figure" | "export" | "upload";
  size_bytes: number;
  created_at: string;
  updated_at: string;
};

export async function listDocuments(
  workspaceId: string,
  query?: string,
): Promise<Document[]> {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  const res = await authorizedFetch(
    `${BASE}/${workspaceId}/documents${params.toString() ? `?${params}` : ""}`,
  );
  if (!res.ok) throw new Error("Failed to list documents");
  const json = await res.json();
  return readItemsArray<Document>(json, "documents");
}

export async function deleteDocument(
  workspaceId: string,
  docId: string,
): Promise<void> {
  const res = await authorizedFetch(
    `${BASE}/${workspaceId}/documents/${docId}`,
    {
      method: "DELETE",
    },
  );
  if (!res.ok) throw new Error("Failed to delete document");
}
