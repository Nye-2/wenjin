"use client";

import type { ExecutionNodeState } from "@/lib/api/types";
import type { PhaseGroup } from "@/lib/execution-phases";
import { PhaseRow } from "./PhaseRow";

export interface InProgressViewProps {
  phases: PhaseGroup[];
  nodeStates: Record<string, ExecutionNodeState>;
  summary?: string;
}

/** Collect all nodes across all phases for the progress bar. */
function collectAllNodes(phases: PhaseGroup[]) {
  const nodes: { id: string; phaseIndex: number }[] = [];
  for (const phase of phases) {
    for (const node of phase.nodes) {
      nodes.push({ id: node.id, phaseIndex: phase.index });
    }
  }
  return nodes;
}

function getSegmentStyle(status: string): {
  background: string;
  animation: string;
} {
  switch (status) {
    case "completed":
      return {
        background: "var(--wjn-success)",
        animation: "none",
      };
    case "running":
      return {
        background: "var(--wjn-blue)",
        animation: "wjn-pulse-soft 1.6s ease-in-out infinite",
      };
    case "failed":
      return {
        background: "var(--wjn-error)",
        animation: "none",
      };
    default:
      return {
        background: "rgba(20, 20, 30, 0.08)",
        animation: "none",
      };
  }
}

export function InProgressView({ phases, nodeStates, summary }: InProgressViewProps) {
  const allNodes = collectAllNodes(phases);

  // Count statuses
  let completed = 0;
  let running = 0;
  for (const { id } of allNodes) {
    const status = nodeStates[id]?.status ?? "pending";
    if (status === "completed") completed++;
    if (status === "running") running++;
  }
  const total = allNodes.length;

  const isRunning = running > 0;

  return (
    <div
      style={{
        fontFamily: "var(--wjn-font-sans)",
        color: "var(--wjn-text)",
      }}
    >
      {/* Progress bar */}
      <div
        style={{
          display: "flex",
          height: 4,
          borderRadius: 2,
          overflow: "hidden",
          background: "var(--wjn-line)",
          marginBottom: 8,
        }}
      >
        {allNodes.map((node) => {
          const status = nodeStates[node.id]?.status ?? "pending";
          const segStyle = getSegmentStyle(status);
          return (
            <div
              key={node.id}
              style={{
                flex: 1,
                background: segStyle.background,
                animation: segStyle.animation,
                transition: "background var(--wjn-duration-medium) var(--wjn-ease-standard)",
              }}
            />
          );
        })}
      </div>

      {/* Status line */}
      <div
        style={{
          fontSize: 11,
          color: "var(--wjn-text-secondary)",
          marginBottom: 16,
        }}
      >
        {completed}/{total} nodes
        {isRunning ? " · processing…" : completed === total && total > 0 ? " · complete" : ""}
      </div>

      {summary ? (
        <div
          style={{
            marginBottom: 14,
            padding: "9px 10px",
            borderRadius: "var(--wjn-radius-md)",
            background: "var(--wjn-accent-soft)",
            color: "var(--wjn-text-secondary)",
            fontSize: 12.5,
            lineHeight: 1.5,
          }}
        >
          {summary}
        </div>
      ) : null}

      {/* Phase rows */}
      <div style={{ display: "flex", flexDirection: "column" }}>
        {phases.length > 0 ? (
          phases.map((phase, i) => (
            <PhaseRow
              key={phase.name}
              phaseName={phase.name}
              phaseIndex={phase.index}
              nodes={phase.nodes}
              nodeStates={nodeStates}
              isLast={i === phases.length - 1}
            />
          ))
        ) : (
          <div
            style={{
              color: "var(--wjn-text-muted)",
              fontSize: 12,
              padding: "4px 0",
            }}
          >
            等待执行图谱...
          </div>
        )}
      </div>
    </div>
  );
}
