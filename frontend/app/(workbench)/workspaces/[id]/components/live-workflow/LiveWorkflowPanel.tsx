"use client";

import { useWorkflowStore } from "@/stores/workflow-store";

import { RunList } from "./RunList";
import { WorkspaceAssets } from "./WorkspaceAssets";

interface LiveWorkflowPanelProps {
  workspaceId: string;
}

export function LiveWorkflowPanel({ workspaceId }: LiveWorkflowPanelProps) {
  const runs = useWorkflowStore((s) => s.runs);
  const currentRunId = useWorkflowStore((s) => s.currentRunId);
  const pausedRunIds = useWorkflowStore((s) => s.pausedRunIds);
  const pauseRun = useWorkflowStore((s) => s.pauseRun);
  const resumeRun = useWorkflowStore((s) => s.resumeRun);

  const hasActiveRun = runs.some(
    (r) => r.status === "running" || r.status === "paused",
  );
  const isPaused = currentRunId ? pausedRunIds.has(currentRunId) : false;

  return (
    <div
      className="flex h-full flex-col"
      style={{
        background: "var(--compute-bg-base)",
        borderLeft: "1px solid var(--compute-border)",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{
          borderBottom: "1px solid var(--compute-border)",
        }}
      >
        <span
          className="text-[13px] font-semibold"
          style={{ color: "var(--compute-text-primary)" }}
        >
          实时工作台
        </span>
        {currentRunId && (
          <button
            onClick={() => {
              if (isPaused) {
                resumeRun(currentRunId);
              } else {
                pauseRun(currentRunId);
              }
            }}
            className="rounded px-2.5 py-1 text-[11px] font-medium transition-opacity hover:opacity-80"
            style={{
              background: "var(--compute-bg-elevated)",
              border: "1px solid var(--compute-border-subtle)",
              color: "var(--compute-text-secondary)",
            }}
          >
            {isPaused ? "继续" : "在下个安全点暂停"}
          </button>
        )}
      </div>

      {/* Body (scrollable) */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {runs.length > 0 && (
          <RunList runs={runs} currentRunId={currentRunId} />
        )}
        <div className={runs.length > 0 ? "mt-3" : ""}>
          <WorkspaceAssets defaultOpen={!hasActiveRun} />
        </div>
      </div>
    </div>
  );
}
