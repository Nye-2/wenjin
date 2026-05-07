"use client";

import { SubagentGrid } from "./SubagentGrid";
import { useWorkflowStore } from "@/stores/workflow-store";
import type { PhaseSnap } from "@/stores/workflow-store-support";

const TERMINAL_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "timed_out",
]);

type PhaseStatus = "done" | "running" | "pending";

function derivePhaseStatus(phase: PhaseSnap): PhaseStatus {
  if (phase.subagents.length === 0) return "pending";
  if (phase.subagents.every((s) => TERMINAL_STATUSES.has(s.status))) {
    return "done";
  }
  return "running";
}

function statusIcon(status: PhaseStatus): string {
  switch (status) {
    case "done":
      return "✓";
    case "running":
      return "◐";
    case "pending":
      return "";
  }
}

interface PhaseListProps {
  runId: string;
  phases: PhaseSnap[];
}

export function PhaseList({ runId, phases }: PhaseListProps) {
  const togglePhase = useWorkflowStore((s) => s.togglePhase);
  const collapsedPhaseIds = useWorkflowStore((s) => s.collapsedPhaseIds);

  return (
    <div className="flex flex-col gap-2">
      {phases.map((phase) => {
        const status = derivePhaseStatus(phase);
        const key = `${runId}:${phase.index}`;
        const isCollapsed = collapsedPhaseIds.has(key);

        // Default: done collapsed, running expanded, pending collapsed.
        // User toggle flips that default.
        const defaultExpanded = status === "running";
        const expanded = isCollapsed ? !defaultExpanded : defaultExpanded;

        const terminalCount = phase.subagents.filter((s) =>
          TERMINAL_STATUSES.has(s.status),
        ).length;
        const totalCount = phase.subagents.length;

        return (
          <div
            key={key}
            data-testid="phase-wrapper"
            data-phase-status={status}
            style={{
              background: "var(--compute-bg-surface)",
              border: "1px solid var(--compute-border-subtle)",
              borderRadius: 6,
            }}
          >
            {/* Header */}
            <button
              onClick={() => togglePhase(runId, phase.index)}
              className="flex w-full items-center justify-between px-3 py-2 text-left"
              style={{ color: "var(--compute-text-primary)" }}
            >
              <div className="flex items-center gap-2 text-[12px] font-medium">
                <span
                  className="inline-flex h-4 w-4 items-center justify-center text-[10px]"
                  style={{ color: "var(--compute-text-muted)" }}
                >
                  {statusIcon(status) || phase.index + 1}
                </span>
                <span>{phase.name}</span>
              </div>
              <span
                className="text-[10px]"
                style={{ color: "var(--compute-text-muted)" }}
              >
                {terminalCount}/{totalCount}
              </span>
            </button>

            {/* Body */}
            {expanded && (
              <div className="px-3 pb-3">
                <SubagentGrid subagents={phase.subagents} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
