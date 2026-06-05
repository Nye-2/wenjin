"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { useShallow } from "zustand/react/shallow";
import { listRuns, type RunRecord } from "@/lib/api/v2/runs";
import {
  mergeRunViews,
  runViewFromExecution,
  runViewFromRunRecord,
  type RunView,
  type RunViewStatus,
} from "@/lib/execution-run-view";
import { useExecutionStore } from "@/stores/execution-store";
import { useRunUiStore } from "@/stores/run-ui-store";
import { useRoomRefreshStore } from "@/stores/room-refresh-store";
import { WorkspaceActionLink } from "../WorkspaceActionLink";

interface RunsDrawerProps {
  workspaceId: string;
  open: boolean;
  onClose: () => void;
}

const STATUS_COLORS: Record<RunViewStatus, string> = {
  launching: "var(--wjn-blue)",
  queued: "var(--wjn-text-muted)",
  completed: "var(--wjn-success)",
  failed_partial: "var(--semantic-warning)",
  failed: "var(--wjn-error)",
  cancelled: "var(--wjn-text-muted)",
  running: "var(--wjn-blue)",
};

const STATUS_BG: Record<RunViewStatus, string> = {
  launching: "var(--wjn-accent-soft)",
  queued: "rgba(100, 100, 120, 0.08)",
  completed: "rgba(34, 197, 94, 0.1)",
  failed_partial: "rgba(198, 138, 26, 0.12)",
  failed: "rgba(239, 68, 68, 0.1)",
  cancelled: "rgba(100, 100, 120, 0.08)",
  running: "var(--wjn-accent-soft)",
};

const STATUS_LABELS: Record<RunViewStatus, string> = {
  launching: "启动中",
  queued: "排队中",
  completed: "已完成",
  failed_partial: "部分完成",
  failed: "失败",
  cancelled: "已取消",
  running: "处理中",
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
  const highlightedRunId = useRunUiStore((state) => state.highlightedRunId);
  const focusRun = useRunUiStore((state) => state.focusRun);
  const refreshCounter = useRoomRefreshStore(
    (state) => state.countersByWorkspace[workspaceId]?.runs ?? 0,
  );
  const executionRecords = useExecutionStore(
    useShallow((state) => Array.from(state.executions.values())),
  );

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
  }, [open, fetchItems, refreshCounter]);

  function handleClose() {
    setVisible(false);
    setTimeout(onClose, 200);
  }

  const runViews = useMemo(() => {
    const historical = new Map<string, RunView>();
    for (const item of items) {
      historical.set(item.id, runViewFromRunRecord(item, workspaceId));
    }

    for (const record of executionRecords) {
      if (record.workspace_id && record.workspace_id !== workspaceId) {
        continue;
      }
      const live = runViewFromExecution(record);
      const existing = historical.get(live.id) ?? null;
      historical.set(live.id, mergeRunViews(live, existing));
    }

    return Array.from(historical.values()).sort((left, right) => {
      if (left.id === highlightedRunId) return -1;
      if (right.id === highlightedRunId) return 1;
      return (right.startedAt || "").localeCompare(left.startedAt || "");
    });
  }, [executionRecords, highlightedRunId, items, workspaceId]);

  const filtered = search
    ? runViews.filter((item) =>
        item.title.toLowerCase().includes(search.toLowerCase()),
      )
    : runViews;

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
        fontFamily: "var(--wjn-font-sans)",
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
            color: "var(--wjn-text)",
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
          placeholder="Search by capability..."
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
          overflowY: "auto",
          padding: "0 16px 16px",
        }}
      >
        {loading && (
          <div
            style={{
              textAlign: "center",
              padding: "40px 0",
              color: "var(--wjn-text-muted)",
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
            No runs found
          </div>
        )}

        {!loading &&
          !error &&
          filtered.map((item) => (
            <div
              key={item.id}
              data-testid="run-item"
              onMouseEnter={() => focusRun(item.id)}
              style={{
                background: "var(--wjn-surface-raised)",
                borderRadius: "var(--wjn-radius-md)",
                border:
                  item.id === highlightedRunId
                    ? "1px solid var(--wjn-accent-line)"
                    : "1px solid rgba(20, 20, 30, 0.06)",
                padding: 12,
                marginBottom: 8,
                boxShadow:
                  item.id === highlightedRunId
                    ? "0 0 0 3px var(--wjn-accent-soft)"
                    : "none",
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
                    color: "var(--wjn-text)",
                  }}
                >
                  {item.title}
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
                  color: "var(--wjn-text-secondary)",
                  marginBottom: 4,
                }}
              >
                {item.summary}
              </div>
              {item.hasPrismChanges ? (
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--wjn-blue)",
                    marginBottom: 6,
                    fontWeight: 600,
                  }}
                >
                  Prism 有 {item.prismReviewCount ?? 1} 项待确认修改
                </div>
              ) : null}
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  fontSize: 11,
                  color: "var(--wjn-text-muted)",
                }}
              >
                {item.startedAt ? <span>{formatTime(item.startedAt)}</span> : null}
                {item.completedAt && (
                  <span>
                    {formatDuration(item.startedAt || "", item.completedAt)}
                  </span>
                )}
              </div>
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 10,
                  marginTop: 8,
                }}
              >
                <WorkspaceActionLink
                  href={`/workspaces/${workspaceId}`}
                  style={actionLinkStyle}
                >
                  查看执行
                </WorkspaceActionLink>
                {item.hasPrismChanges ? (
                  <WorkspaceActionLink
                    href={`/workspaces/${workspaceId}/prism`}
                    style={actionLinkStyle}
                  >
                    打开 Prism
                  </WorkspaceActionLink>
                ) : null}
                <WorkspaceActionLink
                  href={`/workspaces/${workspaceId}?feature=${encodeURIComponent(item.capabilityId ?? "")}&entry=resume&execution_id=${encodeURIComponent(item.id)}`}
                  style={actionLinkStyle}
                >
                  继续提问
                </WorkspaceActionLink>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}

const actionLinkStyle = {
  color: "var(--wjn-blue)",
  fontSize: 12,
  fontWeight: 600,
  textDecoration: "none",
};
