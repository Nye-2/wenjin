"use client";

import { X } from "lucide-react";
import { useEffect, useState, useCallback } from "react";
import {
  listLibraryItems,
  deleteLibraryItem,
  getLibraryItem,
  type LibraryItem,
  type LibraryItemDetail,
} from "@/lib/api/v2/library";
import {
  buildLibraryRoomPreview,
} from "@/lib/workspace-result-preview";
import { useRoomRefreshStore } from "@/stores/room-refresh-store";
import { ResultPreviewDetail } from "../result-preview/ResultPreviewDetail";

interface LibraryDrawerProps {
  workspaceId: string;
  open: boolean;
  initialQuery?: string | null;
  focusItemId?: string | null;
  onClose: () => void;
}

export function LibraryDrawer({
  workspaceId,
  open,
  initialQuery = null,
  focusItemId = null,
  onClose,
}: LibraryDrawerProps) {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [visible, setVisible] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(focusItemId);
  const [hasLoadedList, setHasLoadedList] = useState(false);
  const [detail, setDetail] = useState<LibraryItemDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const refreshCounter = useRoomRefreshStore(
    (state) => state.countersByWorkspace[workspaceId]?.library ?? 0,
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
      const data = await listLibraryItems(workspaceId);
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "资料库加载失败");
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

  async function handleDelete(itemId: string) {
    try {
      await deleteLibraryItem(workspaceId, itemId);
      setItems((prev) => prev.filter((item) => item.id !== itemId));
    } catch {
      setError("文献资料删除失败");
    }
  }

  const filtered = search
    ? items.filter(
        (item) =>
          item.title.toLowerCase().includes(search.toLowerCase()) ||
          item.authors.some((a) =>
            a.toLowerCase().includes(search.toLowerCase()),
          ),
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
    void getLibraryItem(workspaceId, selectedId)
      .then((value) => {
        if (!cancelled) {
          setDetail(value);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setDetailError(
            err instanceof Error ? err.message : "文献详情加载失败",
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
        width: "min(760px, 100%)",
        background: "var(--wjn-surface)",
        borderLeft: "1px solid var(--wjn-line)",
        boxShadow: "var(--wjn-shadow-md)",
        display: "flex",
        flexDirection: "column",
        zIndex: 10,
        transform: visible ? "translateX(0)" : "translateX(100%)",
        transition: "transform 200ms cubic-bezier(0.16, 1, 0.3, 1)",
        fontFamily: "var(--wjn-font-sans)",
        fontSize: 13,
      }}
      role="dialog"
      aria-modal="true"
      aria-label="文献资料"
      data-testid="library-drawer"
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          height: 48,
          padding: "0 16px",
          borderBottom: "1px solid var(--wjn-line)",
        }}
      >
        <span
          style={{
            fontWeight: 600,
            fontSize: 15,
            color: "var(--wjn-text)",
          }}
        >
          文献资料
        </span>
        <button
          type="button"
          aria-label="关闭文献资料"
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
          <X size={16} aria-hidden="true" />
        </button>
      </div>

      {/* Search */}
      <div style={{ padding: "12px 16px" }}>
        <input
          type="text"
          placeholder="按标题或作者搜索"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="drawer-search"
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "8px 12px",
            borderRadius: "var(--wjn-radius-md)",
            border: "1px solid var(--wjn-line)",
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
              正在加载文献资料...
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
              {search ? "没有匹配的文献资料" : "资料库暂无文献"}
            </div>
          )}

          {!loading &&
            !error &&
            filtered.map((item) => (
            <div
              key={item.id}
              onClick={() => setSelectedId(item.id)}
              data-testid="library-item"
              data-item-id={item.id}
              data-focused={item.id === selectedId ? "true" : "false"}
              style={{
                background: "var(--wjn-surface-raised)",
                borderRadius: "var(--wjn-radius-md)",
                border:
                  item.id === selectedId
                    ? "1px solid var(--wjn-accent-line)"
                    : "1px solid var(--wjn-change-neutral-soft)",
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
                    {item.title}
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      color: "var(--wjn-text-secondary)",
                    }}
                  >
                    {item.authors.length > 0 && (
                      <span>{item.authors.join(", ")}</span>
                    )}
                    {item.year && (
                      <span style={{ marginLeft: 8 }}>({item.year})</span>
                    )}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--wjn-text-muted)",
                      marginTop: 4,
                    }}
                  >
                    {item.added_by}
                  </div>
                </div>
                <button
                  type="button"
                  aria-label={`删除 ${item.title}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    void handleDelete(item.id);
                  }}
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
                  删除
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
              正在加载预览...
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
              preview={buildLibraryRoomPreview(detail as Record<string, unknown>)}
            />
          ) : (
            <div
              style={{
                padding: 16,
                color: "var(--wjn-text-muted)",
              }}
            >
              选择一篇文献后，这里会显示来源、摘要和可引用信息。
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
