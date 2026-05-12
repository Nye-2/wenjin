"use client";
import { Handle, Position, type NodeProps } from "@xyflow/react";

export type PhaseNodeData = {
  label: string;
  status: "pending" | "running" | "completed" | "failed";
};

const STATUS_STYLES = {
  pending: {
    orbBg: "transparent",
    orbBorder: "1.5px dashed rgba(20, 20, 30, 0.25)",
    cardBg: "rgba(255, 255, 255, 0.3)",
    cardBorder: "1px dashed rgba(20, 20, 30, 0.15)",
    boxShadow: "none",
    opacity: 0.65,
  },
  running: {
    orbBg: "linear-gradient(135deg, #A78BFA, #7C3AED)",
    orbBorder: "none",
    cardBg: "rgba(255, 255, 255, 0.55)",
    cardBorder: "1px solid rgba(255, 255, 255, 0.6)",
    boxShadow: "0 4px 20px rgba(139, 92, 246, 0.12)",
    opacity: 1,
  },
  completed: {
    orbBg: "linear-gradient(135deg, #4ADE80, #16A34A)",
    orbBorder: "none",
    cardBg: "rgba(255, 255, 255, 0.45)",
    cardBorder: "1px solid rgba(255, 255, 255, 0.5)",
    boxShadow: "none",
    opacity: 1,
  },
  failed: {
    orbBg: "linear-gradient(135deg, #F87171, #DC2626)",
    orbBorder: "none",
    cardBg: "rgba(255, 255, 255, 0.45)",
    cardBorder: "1px solid rgba(220, 38, 38, 0.2)",
    boxShadow: "none",
    opacity: 1,
  },
};

export function PhaseNode({ data }: NodeProps) {
  const { label, status } = data as unknown as PhaseNodeData;
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.pending;

  return (
    <>
      <Handle type="target" position={Position.Top} style={{ visibility: "hidden" }} />
      <div
        style={{
          padding: "10px 16px",
          borderRadius: 14,
          background: style.cardBg,
          border: style.cardBorder,
          boxShadow: style.boxShadow,
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          display: "flex",
          alignItems: "center",
          gap: 10,
          opacity: style.opacity,
          minWidth: 140,
          fontSize: 13,
          fontFamily: "var(--v2-font-sans)",
          color: "var(--v2-text-primary)",
          transition: "all 200ms cubic-bezier(0.16, 1, 0.3, 1)",
        }}
      >
        {/* Status orb */}
        <div
          style={{
            width: 22,
            height: 22,
            borderRadius: "50%",
            background: style.orbBg,
            border: style.orbBorder,
            boxShadow:
              status === "running"
                ? "0 4px 14px rgba(139, 92, 246, 0.4), inset 0 0 0 2px rgba(255, 255, 255, 0.4)"
                : status === "completed"
                  ? "0 4px 14px rgba(22, 163, 74, 0.35), inset 0 0 0 2px rgba(255, 255, 255, 0.4)"
                  : "none",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 11,
            color: "white",
            fontWeight: 700,
            flexShrink: 0,
            animation:
              status === "running"
                ? "v2-pulse-soft 1.6s ease-in-out infinite"
                : "none",
          }}
        >
          {status === "completed" && "✓"}
          {status === "failed" && "✗"}
        </div>
        <span style={{ fontWeight: 500 }}>{label}</span>
      </div>
      <Handle type="source" position={Position.Bottom} style={{ visibility: "hidden" }} />
    </>
  );
}
