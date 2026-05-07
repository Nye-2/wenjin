"use client";

import { PhaseList } from "./PhaseList";
import { useWorkflowStore } from "@/stores/workflow-store";
import type { Run } from "@/stores/workflow-store-support";

interface RunListProps {
  runs: Run[];
  currentRunId: string | null;
}

function RunItem({
  run,
  isCurrent,
  runNumber,
}: {
  run: Run;
  isCurrent: boolean;
  runNumber: number;
}) {
  const toggleRun = useWorkflowStore((s) => s.toggleRun);
  const collapsedRunIds = useWorkflowStore((s) => s.collapsedRunIds);
  const isCollapsed = collapsedRunIds.has(run.id);

  // Default: current expanded, others collapsed. User toggle flips.
  const defaultExpanded = isCurrent;
  const expanded = isCollapsed ? !defaultExpanded : defaultExpanded;

  return (
    <div
      data-testid="run-item"
      style={{
        background: "var(--compute-bg-elevated)",
        border: "1px solid var(--compute-border-subtle)",
        borderRadius: 8,
      }}
    >
      <button
        onClick={() => toggleRun(run.id)}
        className="flex w-full items-center justify-between px-3 py-2.5 text-left"
        style={{ color: "var(--compute-text-primary)" }}
      >
        <span className="text-[12px] font-medium">
          轮 {runNumber} · {run.title}
          {run.status === "completed" && (
            <span className="ml-1" style={{ color: "var(--compute-accent-green)" }}>
              ✓
            </span>
          )}
        </span>
        <span style={{ color: "var(--compute-text-muted)" }}>
          {expanded ? "▾" : "▸"}
        </span>
      </button>
      {expanded && (
        <div className="px-3 pb-3">
          <PhaseList runId={run.id} phases={run.phases} />
        </div>
      )}
    </div>
  );
}

export function RunList({ runs, currentRunId }: RunListProps) {
  return (
    <div data-testid="run-list" className="flex flex-col gap-2">
      {runs.map((run, idx) => (
        <RunItem
          key={run.id}
          run={run}
          isCurrent={run.id === currentRunId}
          runNumber={idx + 1}
        />
      ))}
    </div>
  );
}
