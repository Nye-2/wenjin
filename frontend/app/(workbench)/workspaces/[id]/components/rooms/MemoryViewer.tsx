"use client";

import { useEffect, useState, useCallback } from "react";
import {
  listMemoryFacts,
  deleteMemoryFact,
  type MemoryFact,
} from "@/lib/api/v2/memory";
import { useRoomRefreshStore } from "@/stores/room-refresh-store";

interface MemoryViewerProps {
  workspaceId: string;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

const CATEGORY_COLORS: Record<string, string> = {
  fact: "var(--wjn-blue)",
  preference: "var(--wjn-blue)",
  context: "var(--wjn-success)",
  instruction: "var(--wjn-blue)",
};

const CATEGORY_BACKGROUNDS: Record<string, string> = {
  fact: "var(--wjn-accent-soft)",
  preference: "var(--wjn-accent-soft)",
  context: "var(--wjn-success-soft)",
  instruction: "var(--wjn-accent-soft)",
};

export function MemoryViewer({ workspaceId }: MemoryViewerProps) {
  const [items, setItems] = useState<MemoryFact[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const refreshCounter = useRoomRefreshStore(
    (state) => state.countersByWorkspace[workspaceId]?.memory ?? 0,
  );

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listMemoryFacts(workspaceId);
      setItems(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load memory facts",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems, refreshCounter]);

  async function handleDelete(factId: string) {
    try {
      await deleteMemoryFact(workspaceId, factId);
      setItems((prev) => prev.filter((item) => item.id !== factId));
    } catch {
      setError("Failed to delete memory fact");
    }
  }

  const filtered = search
    ? items.filter((item) =>
        item.content.toLowerCase().includes(search.toLowerCase()),
      )
    : items;

  return (
    <div data-testid="memory-viewer" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Search */}
      <div style={{ padding: "12px 16px" }}>
        <input
          type="text"
          placeholder="Search memory..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="memory-search"
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
            data-testid="memory-loading"
          >
            Loading memory facts...
          </div>
        )}

        {error && (
          <div
            style={{ textAlign: "center", padding: "16px", color: "var(--wjn-error)" }}
            data-testid="memory-error"
          >
            {error}
          </div>
        )}

        {!loading && !error && filtered.length === 0 && (
          <div
            style={{ textAlign: "center", padding: "40px 0", color: "var(--wjn-text-muted)" }}
            data-testid="memory-empty"
          >
            No memory facts found
          </div>
        )}

        {!loading &&
          !error &&
          filtered.map((item) => (
            <div
              key={item.id}
              data-testid="memory-item"
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
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      color: "var(--wjn-text)",
                      fontSize: 13,
                      lineHeight: 1.5,
                      marginBottom: 6,
                    }}
                  >
                    {item.content}
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
                        color: CATEGORY_COLORS[item.category] ?? "var(--wjn-text-secondary)",
                        background: CATEGORY_BACKGROUNDS[item.category] ?? "var(--wjn-surface-subtle)",
                      }}
                    >
                      {item.category}
                    </span>
                    <span>{Math.round(item.confidence * 100)}%</span>
                    <span>{formatDate(item.created_at)}</span>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(item.id)}
                  data-testid="memory-delete"
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
    </div>
  );
}
