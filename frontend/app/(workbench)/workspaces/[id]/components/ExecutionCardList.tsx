"use client";

import { useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import type { ExecutionRecord } from "@/lib/api/types";
import { groupExecutionPhases } from "@/lib/execution-phases";
import { useExecutionStore } from "@/stores/execution-store";
import { useRunUiStore } from "@/stores/run-ui-store";
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
  const currentExecutionId = useExecutionStore((state) => state.currentExecutionId);
  const focusedRunId = useRunUiStore((state) => state.focusedRunId);
  const activeRunId = useRunUiStore((state) => state.activeRunId);
  const executionRecords = useExecutionStore(
    useShallow((state) => Array.from(state.executions.values())),
  );

  const cards = useMemo<Array<{
    key: string;
    record: ExecutionRecord;
    isActive: boolean;
    isExpanded: boolean;
  }>>(() => {
    let relevant = executionRecords.filter((record) => {
      if (record.workspace_id && record.workspace_id !== workspaceId) return false;
      return record.workspace_id === workspaceId || record.id === currentExecutionId;
    });

    const launchingRunId = activeRunId || focusedRunId;
    if (
      launchingRunId &&
      !relevant.some((record) => record.id === launchingRunId)
    ) {
      relevant = [
        makeLaunchingExecutionRecord(launchingRunId, workspaceId),
        ...relevant,
      ];
    }

    const sorted = [...relevant].sort((left, right) => {
      if (focusedRunId && left.id !== right.id) {
        if (left.id === focusedRunId) return -1;
        if (right.id === focusedRunId) return 1;
      }
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
        isExpanded:
          expandedId === record.id ||
          focusedRunId === record.id ||
          (isActive && expandedId === null),
      };
    });
  }, [activeRunId, currentExecutionId, executionRecords, expandedId, focusedRunId, workspaceId]);

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

function makeLaunchingExecutionRecord(
  executionId: string,
  workspaceId: string,
): ExecutionRecord {
  const now = new Date().toISOString();
  return {
    id: executionId,
    user_id: "",
    workspace_id: workspaceId,
    execution_type: "capability",
    feature_id: null,
    display_name: "Lead Agent 执行中",
    status: "running",
    params: {},
    node_states: {},
    artifact_ids: [],
    next_actions: [],
    child_execution_ids: [],
    progress: 0,
    created_at: now,
    started_at: now,
    updated_at: now,
  };
}
