"use client";

import { useEffect, useState, useCallback } from "react";
import { listRuns, type RunRecord } from "@/lib/api/v2/runs";

interface RunsDrawerProps {
  workspaceId: string;
  open: boolean;
  onClose: () => void;
}

const STATUS_COLORS: Record<RunRecord["status"], string> = {
  completed: "var(--v2-status-success-deep)",
  failed_partial: "var(--semantic-warning)",
  failed: "var(--v2-status-error)",
  cancelled: "var(--v2-text-tertiary)",
  running: "var(--v2-status-running-deep)",
};

const STATUS_BG: Record<RunRecord["status"], string> = {
  completed: "rgba(34, 197, 94, 0.1)",
  failed_partial: "rgba(198, 138, 26, 0.12)",
  failed: "rgba(239, 68, 68, 0.1)",
  cancelled: "rgba(100, 100, 120, 0.08)",
  running: "rgba(139, 92, 246, 0.1)",
};

const STATUS_LABELS: Record<RunRecord["status"], string> = {
  completed: "completed",
  failed_partial: "partial",
  failed: "failed",
  cancelled: "cancelled",
  running: "running",
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(
  started: string,
  completed?: string,
): string | null {
  if (!completed) return null;
  const ms =
    new Date(completed).getTime() - new Date(started).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

export function RunsDrawer({
  workspaceId,
  open,
  onClose,
}: RunsDrawerProps) {
  const [items, setItems] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (open) setVisible(true);
  }, [open]);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listRuns(workspaceId);
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load runs");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (open) fetchItems();
  }, [open, fetchItems]);

  function handleClose() {
    setVisible(false);
    setTimeout(onClose, 200);
  }

  const filtered = search
    ? items.filter((item) =>
        item.capability_name.toLowerCase().includes(search.toLowerCase()),
      )
    : items;

  if (!open) return null;

  return (
    <div
      style={{
        position: "absolute",
        right: 0,
        top: 0,
        bottom: 0,
        width: 400,
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
        fontFamily: "var(--v2-font-sans)",
        fontSize: 13,
      }}
      data-testid="runs-drawer"
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
            color: "var(--v2-text-primary)",
          }}
        >
          Runs
        </span>
        <button
          onClick={handleClose}
          data-testid="drawer-close"
          style={{
            border: "none",
            background: "transparent",
            cursor: "pointer",
            fontSize: 16,
            color: "var(--v2-text-tertiary)",
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
          placeholder="Search by capability..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          data-testid="drawer-search"
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
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "0 16px 16px",
        }}
      >
        {loading && (
          <div
            style={{
              textAlign: "center",
              padding: "40px 0",
              color: "var(--v2-text-tertiary)",
            }}
            data-testid="drawer-loading"
          >
            Loading runs...
          </div>
        )}

        {error && (
          <div
            style={{
              textAlign: "center",
              padding: "16px",
              color: "var(--v2-status-error)",
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
              color: "var(--v2-text-tertiary)",
            }}
            data-testid="drawer-empty"
          >
            No runs found
          </div>
        )}

        {!loading &&
          !error &&
          filtered.map((item) => (
            <div
              key={item.id}
              data-testid="run-item"
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
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 6,
                }}
              >
                <span
                  style={{
                    fontWeight: 600,
                    color: "var(--v2-text-primary)",
                  }}
                >
                  {item.capability_name}
                </span>
                <span
                  data-testid="run-status"
                  style={{
                    display: "inline-block",
                    padding: "2px 10px",
                    borderRadius: 10,
                    fontSize: 11,
                    fontWeight: 500,
                    color: STATUS_COLORS[item.status],
                    background: STATUS_BG[item.status],
                  }}
                >
                  {STATUS_LABELS[item.status]}
                </span>
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "var(--v2-text-secondary)",
                  marginBottom: 4,
                }}
              >
                {item.summary}
              </div>
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  fontSize: 11,
                  color: "var(--v2-text-tertiary)",
                }}
              >
                <span>{formatTime(item.started_at)}</span>
                {item.completed_at && (
                  <span>
                    {formatDuration(item.started_at, item.completed_at)}
                  </span>
                )}
                {item.token_usage && (
                  <span>
                    {item.token_usage.input + item.token_usage.output} tokens
                  </span>
                )}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
