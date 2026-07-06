"use client";

import type { ExecutionRecord } from "@/lib/api/types";
import type { PhaseGroup } from "@/lib/execution-phases";
import { runViewFromExecution } from "@/lib/execution-run-view";
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
    completed: { symbol: "✓", color: "var(--wjn-success)", animate: false },
    partial: { symbol: "!", color: "var(--semantic-warning)", animate: false },
    running: { symbol: "⟳", color: "var(--wjn-blue)", animate: true },
    failed: { symbol: "✕", color: "var(--wjn-error)", animate: false },
    cancelled: { symbol: "×", color: "var(--wjn-text-muted)", animate: false },
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
              ? "var(--wjn-accent-soft)"
              : status === "failed"
                ? "rgba(220, 38, 38, 0.1)"
                : "rgba(20, 20, 30, 0.06)",
        color,
        fontSize: status === "running" ? 18 : 16,
        fontWeight: 700,
        fontFamily: "var(--wjn-font-sans)",
        animation: animate ? "wjn-pulse-soft 1.6s ease-in-out infinite" : "none",
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
      color: "var(--wjn-success)",
    },
    partial: {
      label: "Partial",
      bg: "rgba(198, 138, 26, 0.12)",
      color: "var(--semantic-warning)",
    },
    running: {
      label: "Running",
      bg: "var(--wjn-accent-soft)",
      color: "var(--wjn-blue)",
    },
    failed: {
      label: "Failed",
      bg: "rgba(220, 38, 38, 0.1)",
      color: "var(--wjn-error)",
    },
    cancelled: {
      label: "Cancelled",
      bg: "rgba(20, 20, 30, 0.06)",
      color: "var(--wjn-text-muted)",
    },
  };
  const { label, bg, color } = config[status];

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 10px",
        borderRadius: "var(--wjn-radius-pill)",
        background: bg,
        color,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: "18px",
        fontFamily: "var(--wjn-font-sans)",
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
}: ExecutionCardProps) {
  const cardStatus = deriveCardStatus(record);
  const runView = runViewFromExecution(record);
  const nodeCount = phases.reduce((acc, p) => acc + p.nodes.length, 0);

  const title = runView.title;
  const subtitle = [
    record.workspace_type,
    (runView.nodeCount ?? nodeCount) > 0 ? `${runView.nodeCount ?? nodeCount} nodes` : null,
    runView.durationLabel,
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
        border: "1px solid var(--wjn-line)",
        boxShadow: "var(--wjn-shadow-sm)",
        overflow: "hidden",
        transition: "box-shadow var(--wjn-duration-medium) var(--wjn-ease-standard)",
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
              color: "var(--wjn-text)",
              fontFamily: "var(--wjn-font-sans)",
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
              color: "var(--wjn-text-muted)",
              fontFamily: "var(--wjn-font-sans)",
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
              color: "var(--wjn-text-muted)",
              fontSize: 12,
              transition: "transform var(--wjn-duration-medium) var(--wjn-ease-standard)",
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
            borderTop: "1px solid var(--wjn-line)",
            padding: "12px 16px 16px",
            animation: "wjn-panel-in 250ms var(--wjn-ease-standard)",
          }}
        >
          {isTerminalStatus(record.status) ? (
            <CompletedView
              workspaceId={record.workspace_id}
              featureId={record.feature_id}
              executionId={record.id}
              executionStatus={record.status}
              resultSummary={record.result_summary}
              result={record.result}
              reviewItems={record.review_items ?? []}
              nextActions={record.next_actions}
            />
          ) : (
            <InProgressView
              phases={phases}
              nodeStates={record.node_states}
              summary={runView.summary}
            />
          )}
        </div>
      )}
    </div>
  );
}
