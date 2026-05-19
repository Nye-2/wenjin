"use client";

import type { ExecutionRecord } from "@/lib/api/types";
import type { PhaseGroup } from "@/lib/execution-phases";
import { InProgressView } from "./InProgressView";
import { CompletedView } from "./CompletedView";

export interface ExecutionCardProps {
  record: ExecutionRecord;
  phases: PhaseGroup[];
  isExpanded: boolean;
  onToggle: () => void;
  selectedNodeId: string | null;
  selectNode: (id: string | null) => void;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}m ${seconds}s`;
}

function computeDuration(record: ExecutionRecord): string {
  const start = record.started_at ? new Date(record.started_at).getTime() : null;
  if (!start) return "...";
  const end = record.completed_at
    ? new Date(record.completed_at).getTime()
    : Date.now();
  return formatDuration(end - start);
}

function isTerminalStatus(status: string): boolean {
  return ["completed", "failed_partial", "failed", "cancelled"].includes(status);
}

type CardStatus = "completed" | "partial" | "running" | "failed" | "cancelled";

function deriveCardStatus(record: ExecutionRecord): CardStatus {
  if (record.status === "completed") return "completed";
  if (record.status === "failed_partial") return "partial";
  if (record.status === "cancelled") return "cancelled";
  if (record.status === "failed") return "failed";
  return "running";
}

// ── Status icon ────────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: CardStatus }) {
  const config: Record<CardStatus, { symbol: string; color: string; animate: boolean }> = {
    completed: { symbol: "✓", color: "var(--v2-status-success-deep)", animate: false },
    partial: { symbol: "!", color: "var(--semantic-warning)", animate: false },
    running: { symbol: "⟳", color: "var(--v2-accent-purple-700)", animate: true },
    failed: { symbol: "✕", color: "var(--v2-status-error)", animate: false },
    cancelled: { symbol: "×", color: "var(--v2-text-tertiary)", animate: false },
  };
  const { symbol, color, animate } = config[status];

  return (
    <div
      style={{
        width: 32,
        height: 32,
        borderRadius: "50%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background:
          status === "completed"
            ? "rgba(74, 222, 128, 0.12)"
            : status === "partial"
              ? "rgba(198, 138, 26, 0.12)"
            : status === "running"
              ? "var(--v2-accent-purple-100)"
              : status === "failed"
                ? "rgba(220, 38, 38, 0.1)"
                : "rgba(20, 20, 30, 0.06)",
        color,
        fontSize: status === "running" ? 18 : 16,
        fontWeight: 700,
        fontFamily: "var(--v2-font-sans)",
        animation: animate ? "v2-pulse-soft 1.6s ease-in-out infinite" : "none",
        flexShrink: 0,
      }}
    >
      {symbol}
    </div>
  );
}

// ── Status badge pill ──────────────────────────────────────────────────────

function StatusBadge({ status }: { status: CardStatus }) {
  const config: Record<CardStatus, { label: string; bg: string; color: string }> = {
    completed: {
      label: "Completed",
      bg: "rgba(74, 222, 128, 0.12)",
      color: "var(--v2-status-success-deep)",
    },
    partial: {
      label: "Partial",
      bg: "rgba(198, 138, 26, 0.12)",
      color: "var(--semantic-warning)",
    },
    running: {
      label: "Running",
      bg: "var(--v2-accent-purple-100)",
      color: "var(--v2-accent-purple-700)",
    },
    failed: {
      label: "Failed",
      bg: "rgba(220, 38, 38, 0.1)",
      color: "var(--v2-status-error)",
    },
    cancelled: {
      label: "Cancelled",
      bg: "rgba(20, 20, 30, 0.06)",
      color: "var(--v2-text-tertiary)",
    },
  };
  const { label, bg, color } = config[status];

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 10px",
        borderRadius: "var(--v2-radius-pill)",
        background: bg,
        color,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: "18px",
        fontFamily: "var(--v2-font-sans)",
      }}
    >
      {label}
    </span>
  );
}

// ── Component ──────────────────────────────────────────────────────────────

export function ExecutionCard({
  record,
  phases,
  isExpanded,
  onToggle,
  selectedNodeId,
  selectNode,
}: ExecutionCardProps) {
  const cardStatus = deriveCardStatus(record);
  const duration = computeDuration(record);
  const nodeCount = phases.reduce((acc, p) => acc + p.nodes.length, 0);

  const title =
    record.display_name || record.feature_id || "Execution";
  const subtitle = [
    record.workspace_type,
    nodeCount > 0 ? `${nodeCount} nodes` : null,
    duration,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div
      style={{
        background: "rgba(255, 255, 255, 0.7)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderRadius: 16,
        border: "1px solid var(--v2-glass-border)",
        boxShadow: "var(--v2-glass-shadow)",
        overflow: "hidden",
        transition: "box-shadow var(--v2-duration-medium) var(--v2-ease-standard)",
      }}
    >
      {/* ── Card Header ── */}
      <div
        onClick={onToggle}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "14px 16px",
          cursor: "pointer",
          userSelect: "none",
        }}
      >
        {/* Left: status icon */}
        <StatusIcon status={cardStatus} />

        {/* Center: title + subtitle */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: "var(--v2-text-primary)",
              fontFamily: "var(--v2-font-sans)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {title}
          </div>
          <div
            style={{
              fontSize: 12,
              color: "var(--v2-text-tertiary)",
              fontFamily: "var(--v2-font-sans)",
              marginTop: 2,
            }}
          >
            {subtitle}
          </div>
        </div>

        {/* Right: badge + arrow */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <StatusBadge status={cardStatus} />
          <div
            style={{
              width: 20,
              height: 20,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--v2-text-tertiary)",
              fontSize: 12,
              transition: "transform var(--v2-duration-medium) var(--v2-ease-standard)",
              transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
            }}
          >
            &#9662;
          </div>
        </div>
      </div>

      {/* ── Card Body (expanded) ── */}
      {isExpanded && (
        <div
          style={{
            borderTop: "1px solid var(--v2-border-soft)",
            padding: "12px 16px 16px",
            animation: "v2-glass-in 250ms var(--v2-ease-standard)",
          }}
        >
          {isTerminalStatus(record.status) ? (
            <CompletedView
              workspaceId={record.workspace_id}
              featureId={record.feature_id}
              executionId={record.id}
              resultSummary={record.result_summary}
              result={record.result}
              nextActions={record.next_actions}
            />
          ) : (
            <InProgressView
              phases={phases}
              nodeStates={record.node_states}
            />
          )}
        </div>
      )}
    </div>
  );
}
