"use client";

import { useEffect, useState, useCallback } from "react";
import { listDecisions, type Decision } from "@/lib/api/v2/decisions";

interface DecisionsViewerProps {
  workspaceId: string;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
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

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDecisions(workspaceId);
      setItems(data);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load decisions",
      );
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

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
          placeholder="Search decisions..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="decisions-search"
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "8px 12px",
            borderRadius: "var(--v2-radius-md)",
            border: "1px solid rgba(20, 20, 30, 0.08)",
            background: "var(--v2-glass-bg)",
            fontSize: 13,
            fontFamily: "var(--v2-font-sans)",
            color: "var(--v2-text-primary)",
            outline: "none",
          }}
        />
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 16px 16px" }}>
        {loading && (
          <div
            style={{ textAlign: "center", padding: "40px 0", color: "var(--v2-text-tertiary)" }}
            data-testid="decisions-loading"
          >
            Loading decisions...
          </div>
        )}

        {error && (
          <div
            style={{ textAlign: "center", padding: "16px", color: "var(--v2-status-error)" }}
            data-testid="decisions-error"
          >
            {error}
          </div>
        )}

        {!loading && !error && filtered.length === 0 && (
          <div
            style={{ textAlign: "center", padding: "40px 0", color: "var(--v2-text-tertiary)" }}
            data-testid="decisions-empty"
          >
            No decisions found
          </div>
        )}

        {!loading &&
          !error &&
          filtered.map((item) => (
            <div
              key={item.id}
              data-testid="decision-item"
              style={{
                background: "var(--v2-glass-bg)",
                borderRadius: "var(--v2-radius-md)",
                border: "1px solid rgba(20, 20, 30, 0.06)",
                padding: 12,
                marginBottom: 8,
              }}
            >
              <div
                style={{
                  fontWeight: 600,
                  color: "var(--v2-text-primary)",
                  marginBottom: 4,
                  fontSize: 13,
                }}
              >
                {item.key}
              </div>
              <div
                style={{
                  color: "var(--v2-text-secondary)",
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
                    color: "var(--v2-text-tertiary)",
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
                  color: "var(--v2-text-tertiary)",
                }}
              >
                <span
                  style={{
                    display: "inline-block",
                    padding: "1px 8px",
                    borderRadius: 10,
                    fontSize: 11,
                    fontWeight: 500,
                    color: "var(--v2-accent-purple-700)",
                    background: "var(--v2-accent-purple-100)",
                  }}
                >
                  {Math.round(item.confidence * 100)}% confidence
                </span>
                <span>{formatDate(item.created_at)}</span>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
