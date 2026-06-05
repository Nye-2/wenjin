"use client";

import { useEffect, useState, useCallback } from "react";
import {
  listDocuments,
  deleteDocument,
  getDocument,
  type Document,
  type DocumentDetail,
} from "@/lib/api/v2/documents";
import { buildDocumentRoomPreview } from "@/lib/workspace-result-preview";
import { useRoomRefreshStore } from "@/stores/room-refresh-store";
import { ResultPreviewDetail } from "../result-preview/ResultPreviewDetail";

interface DocumentsDrawerProps {
  workspaceId: string;
  open: boolean;
  initialQuery?: string | null;
  focusItemId?: string | null;
  onClose: () => void;
}

const KIND_LABELS: Record<Document["doc_kind"], string> = {
  draft: "Draft",
  outline: "Outline",
  figure: "Figure",
  export: "Export",
  upload: "Upload",
};

const KIND_COLORS: Record<Document["doc_kind"], string> = {
  draft: "var(--wjn-blue)",
  outline: "var(--wjn-blue)",
  figure: "var(--wjn-success)",
  export: "var(--wjn-blue)",
  upload: "var(--wjn-text-secondary)",
};

const KIND_BACKGROUNDS: Record<Document["doc_kind"], string> = {
  draft: "var(--wjn-accent-soft)",
  outline: "var(--wjn-accent-soft)",
  figure: "var(--wjn-success-soft)",
  export: "var(--wjn-accent-soft)",
  upload: "var(--wjn-surface-subtle)",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function DocumentsDrawer({
  workspaceId,
  open,
  initialQuery = null,
  focusItemId = null,
  onClose,
}: DocumentsDrawerProps) {
  const [items, setItems] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [visible, setVisible] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(focusItemId);
  const [hasLoadedList, setHasLoadedList] = useState(false);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const refreshCounter = useRoomRefreshStore(
    (state) => state.countersByWorkspace[workspaceId]?.documents ?? 0,
  );

  useEffect(() => {
    if (open) setVisible(true);
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    setSearch(initialQuery ?? "");
    setSelectedId(focusItemId ?? null);
  }, [focusItemId, initialQuery, open]);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    setHasLoadedList(false);
    try {
      const data = await listDocuments(workspaceId);
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setLoading(false);
      setHasLoadedList(true);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (open) fetchItems();
  }, [open, fetchItems, refreshCounter]);

  function handleClose() {
    setVisible(false);
    setTimeout(onClose, 200);
  }

  async function handleDelete(docId: string) {
    try {
      await deleteDocument(workspaceId, docId);
      setItems((prev) => prev.filter((item) => item.id !== docId));
    } catch {
      setError("Failed to delete document");
    }
  }

  const filtered = search
    ? items.filter((item) =>
        item.name.toLowerCase().includes(search.toLowerCase()),
      )
    : items;

  useEffect(() => {
    if (!open || !hasLoadedList) {
      return;
    }
    if (filtered.length === 0) {
      setSelectedId(null);
      return;
    }
    setSelectedId((current) => {
      if (current && filtered.some((item) => item.id === current)) {
        return current;
      }
      if (focusItemId && filtered.some((item) => item.id === focusItemId)) {
        return focusItemId;
      }
      return filtered[0].id;
    });
  }, [filtered, focusItemId, hasLoadedList, open]);

  useEffect(() => {
    if (!open || !selectedId) {
      setDetail(null);
      setDetailError(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    void getDocument(workspaceId, selectedId)
      .then((value) => {
        if (!cancelled) {
          setDetail(value);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setDetailError(
            err instanceof Error ? err.message : "Failed to load document",
          );
          setDetail(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setDetailLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, selectedId, workspaceId]);

  if (!open) return null;

  return (
    <div
      style={{
        position: "absolute",
        right: 0,
        top: 0,
        bottom: 0,
        width: 760,
        background: "rgba(255, 255, 255, 0.92)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderLeft: "1px solid rgba(20, 20, 30, 0.08)",
        boxShadow: "0 8px 32px rgba(20, 20, 30, 0.08)",
        display: "flex",
        flexDirection: "column",
        zIndex: 10,
        transform: visible ? "translateX(0)" : "translateX(100%)",
        transition: "transform 200ms cubic-bezier(0.16, 1, 0.3, 1)",
        fontFamily: "var(--wjn-font-sans)",
        fontSize: 13,
      }}
      data-testid="documents-drawer"
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          height: 48,
          padding: "0 16px",
          borderBottom: "1px solid rgba(20, 20, 30, 0.08)",
        }}
      >
        <span
          style={{
            fontWeight: 600,
            fontSize: 15,
            color: "var(--wjn-text)",
          }}
        >
          Documents
        </span>
        <button
          onClick={handleClose}
          data-testid="drawer-close"
          style={{
            border: "none",
            background: "transparent",
            cursor: "pointer",
            fontSize: 16,
            color: "var(--wjn-text-muted)",
            lineHeight: 1,
            padding: 4,
          }}
        >
          ✕
        </button>
      </div>

      {/* Search */}
      <div style={{ padding: "12px 16px" }}>
        <input
          type="text"
          placeholder="Search by name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="drawer-search"
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "8px 12px",
            borderRadius: "var(--wjn-radius-md)",
            border: "1px solid rgba(20, 20, 30, 0.08)",
            background: "var(--wjn-surface-raised)",
            fontSize: 13,
            fontFamily: "var(--wjn-font-sans)",
            color: "var(--wjn-text)",
            outline: "none",
          }}
        />
      </div>

      {/* Content */}
      <div
        style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "280px minmax(0, 1fr)",
          gap: 12,
          padding: "0 16px 16px",
          minHeight: 0,
        }}
      >
        <div style={{ minHeight: 0, overflowY: "auto", paddingRight: 4 }}>
          {loading && (
            <div
              style={{
                textAlign: "center",
                padding: "40px 0",
                color: "var(--wjn-text-muted)",
              }}
              data-testid="drawer-loading"
            >
              Loading documents...
            </div>
          )}

          {error && (
            <div
              style={{
                textAlign: "center",
                padding: "16px",
                color: "var(--wjn-error)",
              }}
              data-testid="drawer-error"
            >
              {error}
            </div>
          )}

          {!loading && !error && filtered.length === 0 && (
            <div
              style={{
                textAlign: "center",
                padding: "40px 0",
                color: "var(--wjn-text-muted)",
              }}
              data-testid="drawer-empty"
            >
              No documents found
            </div>
          )}

          {!loading &&
            !error &&
            filtered.map((item) => (
            <div
              key={item.id}
              onClick={() => setSelectedId(item.id)}
              data-testid="document-item"
              data-item-id={item.id}
              data-focused={item.id === selectedId ? "true" : "false"}
              style={{
                background: "var(--wjn-surface-raised)",
                borderRadius: "var(--wjn-radius-md)",
                border:
                  item.id === selectedId
                    ? "1px solid var(--wjn-accent-line)"
                    : "1px solid rgba(20, 20, 30, 0.06)",
                boxShadow:
                  item.id === selectedId
                    ? "0 0 0 3px var(--wjn-accent-soft)"
                    : "none",
                padding: 12,
                marginBottom: 8,
                cursor: "pointer",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontWeight: 600,
                      color: "var(--wjn-text)",
                      marginBottom: 4,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {item.name}
                  </div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      fontSize: 12,
                      color: "var(--wjn-text-secondary)",
                    }}
                  >
                    <span
                      style={{
                        display: "inline-block",
                        padding: "1px 8px",
                        borderRadius: 10,
                        fontSize: 11,
                        fontWeight: 500,
                        color: KIND_COLORS[item.doc_kind],
                        background: KIND_BACKGROUNDS[item.doc_kind],
                      }}
                    >
                      {KIND_LABELS[item.doc_kind]}
                    </span>
                    <span>{formatBytes(item.size_bytes)}</span>
                    <span>{formatDate(item.updated_at)}</span>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(item.id)}
                  data-testid="item-delete"
                  style={{
                    border: "none",
                    background: "transparent",
                    cursor: "pointer",
                    color: "var(--wjn-text-muted)",
                    fontSize: 12,
                    padding: "2px 4px",
                    flexShrink: 0,
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
            ))}
        </div>

        <div style={{ minHeight: 0, overflowY: "auto" }}>
          {detailLoading ? (
            <div
              style={{
                padding: 16,
                color: "var(--wjn-text-muted)",
              }}
            >
              Loading preview...
            </div>
          ) : detailError ? (
            <div
              style={{
                padding: 16,
                color: "var(--wjn-error)",
              }}
            >
              {detailError}
            </div>
          ) : detail ? (
            <ResultPreviewDetail
              preview={buildDocumentRoomPreview(detail as Record<string, unknown>)}
            />
          ) : (
            <div
              style={{
                padding: 16,
                color: "var(--wjn-text-muted)",
              }}
            >
              Select a document to preview it here.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
