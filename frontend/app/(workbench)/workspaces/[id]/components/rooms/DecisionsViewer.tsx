"use client";

import { useEffect, useState, useCallback } from "react";
import { listDecisions, type Decision } from "@/lib/api/v2/decisions";
import { useRoomRefreshStore } from "@/stores/room-refresh-store";

interface DecisionsViewerProps {
  workspaceId: string;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("zh-CN", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function DecisionsViewer({ workspaceId }: DecisionsViewerProps) {
  const [items, setItems] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const refreshCounter = useRoomRefreshStore(
    (state) => state.countersByWorkspace[workspaceId]?.decisions ?? 0,
  );

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDecisions(workspaceId);
      setItems(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "决策记录加载失败",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems, refreshCounter]);

  const filtered = search
    ? items.filter((item) =>
        item.key.toLowerCase().includes(search.toLowerCase()),
      )
    : items;

  return (
    <div data-testid="decisions-viewer" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Search */}
      <div style={{ padding: "12px 16px" }}>
        <input
          type="text"
          placeholder="搜索决策记录"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="decisions-search"
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
      <div style={{ flex: 1, overflowY: "auto", padding: "0 16px 16px" }}>
        {loading && (
          <div
            style={{ textAlign: "center", padding: "40px 0", color: "var(--wjn-text-muted)" }}
            data-testid="decisions-loading"
          >
            正在加载决策记录...
          </div>
        )}

        {error && (
          <div
            style={{ textAlign: "center", padding: "16px", color: "var(--wjn-error)" }}
            data-testid="decisions-error"
          >
            {error}
          </div>
        )}

        {!loading && !error && filtered.length === 0 && (
          <div
            style={{ textAlign: "center", padding: "40px 0", color: "var(--wjn-text-muted)" }}
            data-testid="decisions-empty"
          >
            {search ? "没有匹配的决策记录" : "暂无决策记录"}
          </div>
        )}

        {!loading &&
          !error &&
          filtered.map((item) => (
            <div
              key={item.id}
              data-testid="decision-item"
              style={{
                background: "var(--wjn-surface-raised)",
                borderRadius: "var(--wjn-radius-md)",
                border: "1px solid rgba(20, 20, 30, 0.06)",
                padding: 12,
                marginBottom: 8,
              }}
            >
              <div
                style={{
                  fontWeight: 600,
                  color: "var(--wjn-text)",
                  marginBottom: 4,
                  fontSize: 13,
                }}
              >
                {item.key}
              </div>
              <div
                style={{
                  color: "var(--wjn-text-secondary)",
                  fontSize: 13,
                  marginBottom: 6,
                  lineHeight: 1.5,
                }}
              >
                {item.value}
              </div>
              {item.rationale && (
                <div
                  style={{
                    color: "var(--wjn-text-muted)",
                    fontSize: 12,
                    fontStyle: "italic",
                    marginBottom: 6,
                    lineHeight: 1.4,
                  }}
                >
                  {item.rationale}
                </div>
              )}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: 12,
                  color: "var(--wjn-text-muted)",
                }}
              >
                <span
                  style={{
                    display: "inline-block",
                    padding: "1px 8px",
                    borderRadius: 10,
                    fontSize: 11,
                    fontWeight: 500,
                    color: "var(--wjn-blue)",
                    background: "var(--wjn-accent-soft)",
                  }}
                >
                  可信度 {Math.round(item.confidence * 100)}%
                </span>
                <span>{formatDate(item.created_at)}</span>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
