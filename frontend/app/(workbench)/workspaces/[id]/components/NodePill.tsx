"use client";

import type { ExecutionNodeState } from "@/lib/api/types";

export interface NodePillProps {
  id: string;
  label: string;
  state: ExecutionNodeState | undefined;
  isSelected: boolean;
  onClick: () => void;
}

const DOT_STYLES: Record<string, { bg: string; border: string; boxShadow: string; animation: string }> = {
  completed: {
    bg: "var(--wjn-success)",
    border: "none",
    boxShadow: "none",
    animation: "none",
  },
  running: {
    bg: "var(--wjn-blue)",
    border: "none",
    boxShadow: "none",
    animation: "wjn-pulse-soft 1.6s ease-in-out infinite",
  },
  failed: {
    bg: "var(--wjn-error)",
    border: "none",
    boxShadow: "none",
    animation: "none",
  },
  pending: {
    bg: "transparent",
    border: "1.5px dashed rgba(20, 20, 30, 0.25)",
    boxShadow: "none",
    animation: "none",
  },
};

export function NodePill({ label, state, isSelected, onClick }: NodePillProps) {
  const status = state?.status ?? "pending";
  const dotStyle = DOT_STYLES[status] ?? DOT_STYLES.pending;

  const statusColor =
    status === "completed"
      ? "var(--wjn-success)"
      : status === "running"
        ? "var(--wjn-blue)"
        : status === "failed"
          ? "var(--wjn-error)"
          : "var(--wjn-text-muted)";

  return (
    <button
      onClick={onClick}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 10px 4px 6px",
        borderRadius: "var(--wjn-radius-pill)",
        background: isSelected
          ? "var(--wjn-accent-soft)"
          : "var(--wjn-surface-raised)",
        border: isSelected
          ? "1px solid var(--wjn-accent-line)"
          : "1px solid var(--wjn-line)",
        cursor: "pointer",
        fontFamily: "var(--wjn-font-sans)",
        fontSize: 12,
        fontWeight: 500,
        color: isSelected ? statusColor : "var(--wjn-text)",
        transition: "all var(--wjn-duration-fast) var(--wjn-ease-standard)",
        outline: "none",
        lineHeight: 1,
      }}
    >
      {/* Status dot */}
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: dotStyle.bg,
          border: dotStyle.border,
          boxShadow: dotStyle.boxShadow,
          animation: dotStyle.animation,
          flexShrink: 0,
        }}
      />
      {label}
    </button>
  );
}
