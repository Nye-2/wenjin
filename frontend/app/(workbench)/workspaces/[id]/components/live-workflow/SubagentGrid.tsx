"use client";

import { useState } from "react";

import { SubagentCard } from "./SubagentCard";
import type { SubagentSnap } from "@/stores/workflow-store-support";

const TERMINAL_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "timed_out",
]);

function isTerminal(sa: SubagentSnap): boolean {
  return TERMINAL_STATUSES.has(sa.status);
}

interface SubagentGridProps {
  subagents: SubagentSnap[];
}

export function SubagentGrid({ subagents }: SubagentGridProps) {
  const [expanded, setExpanded] = useState(false);

  const shouldFold = subagents.length >= 6;
  const terminal = subagents.filter(isTerminal);
  const nonTerminal = subagents.filter((s) => !isTerminal(s));

  const visible = shouldFold && !expanded ? nonTerminal : subagents;
  const foldedCount = shouldFold && !expanded ? terminal.length : 0;

  const gridCols =
    visible.length >= 2
      ? "grid-cols-2"
      : "grid-cols-1";

  return (
    <div data-testid="subagent-grid">
      <div className={`grid ${gridCols} gap-2`}>
        {visible.map((sa) => (
          <SubagentCard key={sa.task_id} subagent={sa} />
        ))}
      </div>
      {foldedCount > 0 && (
        <button
          onClick={() => setExpanded(true)}
          style={{
            color: "var(--compute-text-muted)",
            background: "var(--compute-bg-surface)",
            border: "1px solid var(--compute-border-subtle)",
          }}
          className="mt-2 w-full rounded px-2 py-1.5 text-[11px] text-center transition-colors hover:opacity-80"
        >
          ▾ {foldedCount} 个已完成（点开查看）
        </button>
      )}
    </div>
  );
}
