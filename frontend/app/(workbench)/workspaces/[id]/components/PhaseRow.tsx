"use client";

import { useState } from "react";
import type { ExecutionGraphNode, ExecutionNodeState } from "@/lib/api/types";
import { NodePill } from "./NodePill";
import { NodeInlineDetail } from "./NodeInlineDetail";

export interface PhaseRowProps {
  phaseName: string;
  phaseIndex: number;
  nodes: ExecutionGraphNode[];
  nodeStates: Record<string, ExecutionNodeState>;
  isLast: boolean;
  loopInfo?: string | null;
}

function getPhaseStatus(
  nodes: ExecutionGraphNode[],
  nodeStates: Record<string, ExecutionNodeState>,
): "completed" | "running" | "pending" {
  let hasRunning = false;
  let allCompleted = true;
  for (const node of nodes) {
    const status = nodeStates[node.id]?.status ?? "pending";
    if (status === "running") hasRunning = true;
    if (status !== "completed") allCompleted = false;
  }
  if (hasRunning) return "running";
  if (allCompleted) return "completed";
  return "pending";
}

const PHASE_DOT_STYLES = {
  completed: {
    bg: "linear-gradient(135deg, #4ADE80, #16A34A)",
    boxShadow: "0 3px 12px rgba(22, 163, 74, 0.35), inset 0 0 0 2px rgba(255, 255, 255, 0.4)",
    animation: "none",
    content: "✓" as string,
    color: "white" as string,
  },
  running: {
    bg: "linear-gradient(135deg, #A78BFA, #7C3AED)",
    boxShadow: "0 3px 12px rgba(139, 92, 246, 0.4), inset 0 0 0 2px rgba(255, 255, 255, 0.4)",
    animation: "v2-pulse-soft 1.6s ease-in-out infinite",
    content: "" as string,
    color: "white" as string,
  },
  pending: {
    bg: "rgba(20, 20, 30, 0.06)",
    boxShadow: "none",
    animation: "none",
    content: "" as string,
    color: "var(--v2-text-tertiary)" as string,
  },
};

export function PhaseRow({
  phaseName,
  phaseIndex,
  nodes,
  nodeStates,
  isLast,
  loopInfo,
}: PhaseRowProps) {
  const [expandedNodeId, setExpandedNodeId] = useState<string | null>(null);

  const phaseStatus = getPhaseStatus(nodes, nodeStates);
  const dotStyle = PHASE_DOT_STYLES[phaseStatus];

  // Find thinking text for running nodes
  const thinkingPreview = nodes
    .map((n) => nodeStates[n.id])
    .filter((s) => s?.status === "running" && s.thinking)
    .map((s) => s!.thinking!)[0];

  const handlePillClick = (nodeId: string) => {
    setExpandedNodeId((prev) => (prev === nodeId ? null : nodeId));
  };

  return (
    <div style={{ display: "flex", gap: 12 }}>
      {/* Timeline rail */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          width: 22,
          flexShrink: 0,
        }}
      >
        {/* Phase dot */}
        <div
          style={{
            width: 22,
            height: 22,
            borderRadius: "50%",
            background: dotStyle.bg,
            boxShadow: dotStyle.boxShadow,
            animation: dotStyle.animation,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 11,
            fontWeight: 700,
            color: dotStyle.color,
            flexShrink: 0,
          }}
        >
          {phaseStatus === "completed" ? (
            "✓"
          ) : phaseStatus === "running" ? (
            phaseIndex + 1
          ) : (
            phaseIndex + 1
          )}
        </div>

        {/* Vertical line to next phase */}
        {!isLast && (
          <div
            style={{
              width: 2,
              flex: 1,
              minHeight: 28,
              background:
                phaseStatus === "completed"
                  ? "linear-gradient(180deg, rgba(74, 222, 128, 0.5), rgba(74, 222, 128, 0.1))"
                  : "var(--v2-border-soft)",
              borderRadius: 1,
            }}
          />
        )}
      </div>

      {/* Phase content */}
      <div style={{ flex: 1, paddingBottom: isLast ? 0 : 16 }}>
        {/* Phase title + loop label */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span
            style={{
              fontFamily: "var(--v2-font-sans)",
              fontSize: 13,
              fontWeight: 600,
              color: "var(--v2-text-primary)",
            }}
          >
            {phaseName}
          </span>
          {loopInfo && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 3,
                padding: "2px 8px",
                borderRadius: "var(--v2-radius-pill)",
                background: "rgba(250, 204, 21, 0.12)",
                border: "1px solid rgba(250, 204, 21, 0.25)",
                fontSize: 10,
                fontWeight: 600,
                fontFamily: "var(--v2-font-sans)",
                color: "#A16207",
              }}
            >
              {"↺"} {loopInfo}
            </span>
          )}
        </div>

        {/* Node pills row */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {nodes.map((node) => {
            const state = nodeStates[node.id];
            return (
              <div key={node.id}>
                <NodePill
                  id={node.id}
                  label={node.label ?? node.id}
                  state={state}
                  isSelected={expandedNodeId === node.id}
                  onClick={() => handlePillClick(node.id)}
                />
                {expandedNodeId === node.id && state && (
                  <NodeInlineDetail state={state} />
                )}
              </div>
            );
          })}
        </div>

        {/* Thinking preview */}
        {thinkingPreview && (
          <div
            style={{
              marginTop: 8,
              padding: "6px 10px",
              borderRadius: "var(--v2-radius-sm)",
              background: "rgba(139, 92, 246, 0.04)",
              borderLeft: "3px solid var(--v2-accent-purple-300)",
              fontFamily: "var(--v2-font-mono)",
              fontSize: 11,
              lineHeight: 1.5,
              color: "var(--v2-text-secondary)",
              display: "-webkit-box",
              WebkitLineClamp: 3,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            {thinkingPreview}
          </div>
        )}
      </div>
    </div>
  );
}
