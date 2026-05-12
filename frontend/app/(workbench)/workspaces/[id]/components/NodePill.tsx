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
    bg: "linear-gradient(135deg, #4ADE80, #16A34A)",
    border: "none",
    boxShadow: "0 2px 8px rgba(22, 163, 74, 0.35)",
    animation: "none",
  },
  running: {
    bg: "linear-gradient(135deg, #A78BFA, #7C3AED)",
    border: "none",
    boxShadow: "0 2px 8px rgba(139, 92, 246, 0.4)",
    animation: "v2-pulse-soft 1.6s ease-in-out infinite",
  },
  failed: {
    bg: "linear-gradient(135deg, #F87171, #DC2626)",
    border: "none",
    boxShadow: "0 2px 8px rgba(220, 38, 38, 0.35)",
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
      ? "var(--v2-status-success-deep)"
      : status === "running"
        ? "var(--v2-status-running-deep)"
        : status === "failed"
          ? "var(--v2-status-error)"
          : "var(--v2-status-idle)";

  return (
    <button
      onClick={onClick}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 10px 4px 6px",
        borderRadius: "var(--v2-radius-pill)",
        background: isSelected
          ? "rgba(139, 92, 246, 0.1)"
          : "var(--v2-glass-bg-subtle)",
        border: isSelected
          ? "1px solid rgba(139, 92, 246, 0.25)"
          : "1px solid var(--v2-border-soft)",
        cursor: "pointer",
        fontFamily: "var(--v2-font-sans)",
        fontSize: 12,
        fontWeight: 500,
        color: isSelected ? statusColor : "var(--v2-text-primary)",
        transition: "all var(--v2-duration-fast) var(--v2-ease-standard)",
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
