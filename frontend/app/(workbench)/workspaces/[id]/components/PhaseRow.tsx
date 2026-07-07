"use client";

import { useState } from "react";
import type { ExecutionGraphNode, ExecutionNodeState } from "@/lib/api/types";
import { safeRuntimeText } from "@/lib/runtime-payload-safety";
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
    bg: "var(--wjn-success)",
    boxShadow: "none",
    animation: "none",
    content: "✓" as string,
    color: "white" as string,
  },
  running: {
    bg: "var(--wjn-blue)",
    boxShadow: "none",
    animation: "wjn-pulse-soft 1.6s ease-in-out infinite",
    content: "" as string,
    color: "white" as string,
  },
  pending: {
    bg: "rgba(20, 20, 30, 0.06)",
    boxShadow: "none",
    animation: "none",
    content: "" as string,
    color: "var(--wjn-text-muted)" as string,
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

  const runningThinking = nodes
    .map((n) => nodeStates[n.id])
    .filter((s) => s?.status === "running" && s.thinking)
    .map((s) => s!.thinking!);
  const thinkingPreview =
    runningThinking
      .map((thinking) => safeRuntimeText(thinking, 260))
      .find((thinking): thinking is string => Boolean(thinking)) ??
    (runningThinking.length > 0 ? "当前步骤正在处理。" : null);

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
                  ? "var(--wjn-risk-low-line)"
                  : "var(--wjn-line)",
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
              fontFamily: "var(--wjn-font-sans)",
              fontSize: 13,
              fontWeight: 600,
              color: "var(--wjn-text)",
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
                borderRadius: "var(--wjn-radius-pill)",
                background: "rgba(250, 204, 21, 0.12)",
                border: "1px solid rgba(250, 204, 21, 0.25)",
                fontSize: 10,
                fontWeight: 600,
                fontFamily: "var(--wjn-font-sans)",
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
              borderRadius: "var(--wjn-radius)",
              background: "rgba(44, 93, 160, 0.04)",
              border: "1px solid var(--wjn-accent-line)",
              fontFamily: "var(--wjn-font-mono)",
              fontSize: 11,
              lineHeight: 1.5,
              color: "var(--wjn-text-secondary)",
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
