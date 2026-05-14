"use client";

import type { ExecutionNodeState } from "@/lib/api/types";
import type { PhaseGroup } from "@/lib/execution-phases";
import { PhaseRow } from "./PhaseRow";

export interface InProgressViewProps {
  phases: PhaseGroup[];
  nodeStates: Record<string, ExecutionNodeState>;
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
        background: "linear-gradient(135deg, #4ADE80, #16A34A)",
        animation: "none",
      };
    case "running":
      return {
        background: "linear-gradient(135deg, #A78BFA, #7C3AED)",
        animation: "v2-pulse-soft 1.6s ease-in-out infinite",
      };
    case "failed":
      return {
        background: "linear-gradient(135deg, #F87171, #DC2626)",
        animation: "none",
      };
    default:
      return {
        background: "rgba(20, 20, 30, 0.08)",
        animation: "none",
      };
  }
}

export function InProgressView({ phases, nodeStates }: InProgressViewProps) {
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
        fontFamily: "var(--v2-font-sans)",
        color: "var(--v2-text-primary)",
      }}
    >
      {/* Progress bar */}
      <div
        style={{
          display: "flex",
          height: 4,
          borderRadius: 2,
          overflow: "hidden",
          background: "var(--v2-border-default)",
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
                transition: "background var(--v2-duration-medium) var(--v2-ease-standard)",
              }}
            />
          );
        })}
      </div>

      {/* Status line */}
      <div
        style={{
          fontSize: 11,
          color: "var(--v2-text-secondary)",
          marginBottom: 16,
        }}
      >
        {completed}/{total} nodes
        {isRunning ? " · processing…" : completed === total && total > 0 ? " · complete" : ""}
      </div>

      {/* Phase rows */}
      <div style={{ display: "flex", flexDirection: "column" }}>
        {phases.map((phase, i) => (
          <PhaseRow
            key={phase.name}
            phaseName={phase.name}
            phaseIndex={phase.index}
            nodes={phase.nodes}
            nodeStates={nodeStates}
            isLast={i === phases.length - 1}
          />
        ))}
      </div>
    </div>
  );
}
