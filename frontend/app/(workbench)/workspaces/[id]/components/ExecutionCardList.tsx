"use client";

import { useMemo, useState } from "react";

import type { ExecutionRecord } from "@/lib/api/types";
import { groupExecutionPhases } from "@/lib/execution-phases";
import { useExecutionStore } from "@/stores/execution-store";
import { ExecutionCard } from "./ExecutionCard";

interface ExecutionCardListProps {
  workspaceId: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function isTerminalStatus(status: string): boolean {
  return ["completed", "failed_partial", "failed", "cancelled"].includes(status);
}

// ── Component ──────────────────────────────────────────────────────────────

export function ExecutionCardList({ workspaceId }: ExecutionCardListProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const currentExecutionId = useExecutionStore((s) => s.currentExecutionId);
  const executions = useExecutionStore((s) => s.executions);
  const executionRecords = useMemo(
    () => Array.from(executions.values()),
    [executions],
  );

  const cards = useMemo<Array<{
    key: string;
    record: ExecutionRecord;
    isActive: boolean;
    isExpanded: boolean;
  }>>(() => {
    const relevant = executionRecords.filter((record) => {
      if (record.workspace_id && record.workspace_id !== workspaceId) return false;
      return record.workspace_id === workspaceId || record.id === currentExecutionId;
    });

    const sorted = [...relevant].sort((left, right) => {
      const leftActive = !isTerminalStatus(left.status);
      const rightActive = !isTerminalStatus(right.status);
      if (leftActive !== rightActive) return leftActive ? -1 : 1;
      return (right.created_at || "").localeCompare(left.created_at || "");
    });

    return sorted.map((record) => {
      const isActive = !isTerminalStatus(record.status);
      return {
        key: record.id,
        record,
        isActive,
        isExpanded: expandedId === record.id || (isActive && expandedId === null),
      };
    });
  }, [currentExecutionId, executionRecords, expandedId, workspaceId]);

  if (cards.length === 0) return null;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 8,
        width: "100%",
      }}
    >
      {cards.map((card) => (
        <ExecutionCard
          key={card.key}
          record={card.record}
          phases={groupExecutionPhases(card.record)}
          isExpanded={card.isExpanded}
          onToggle={() =>
            setExpandedId((prev) => (prev === card.key ? null : card.key))
          }
          selectedNodeId={selectedNodeId}
          selectNode={setSelectedNodeId}
        />
      ))}
    </div>
  );
}
