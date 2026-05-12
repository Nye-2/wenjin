"use client";

import { useMemo, useState } from "react";
import { useExecutionStore } from "@/stores/execution-store";
import { useExecutionStream } from "./useExecutionStream";
import type { ExecutionGraphNode, ExecutionRecord } from "@/lib/api/types";

export interface PhaseGroup {
  name: string;
  index: number;
  nodes: ExecutionGraphNode[];
}

export interface UseExecutionStreamV2Return {
  record: ExecutionRecord | null;
  phases: PhaseGroup[];
  executionId: string | null;
  selectedNodeId: string | null;
  selectNode: (id: string | null) => void;
}

export function useExecutionStreamV2(
  _workspaceId: string,
  executionId?: string | null,
): UseExecutionStreamV2Return {
  const currentId =
    executionId ?? useExecutionStore((s) => s.currentExecutionId) ?? null;
  useExecutionStream(currentId);

  const record = useExecutionStore((s) =>
    currentId ? s.executions.get(currentId) ?? null : null,
  );

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const phases = useMemo<PhaseGroup[]>(() => {
    if (!record?.graph_structure?.nodes) return [];
    const phaseMap = new Map<string, { index: number; nodes: ExecutionGraphNode[] }>();
    let idx = 0;
    for (const node of record.graph_structure.nodes) {
      const phaseName = node.phase || "default";
      if (!phaseMap.has(phaseName)) {
        phaseMap.set(phaseName, { index: idx++, nodes: [] });
      }
      phaseMap.get(phaseName)!.nodes.push(node);
    }
    return Array.from(phaseMap.entries()).map(([name, data]) => ({
      name,
      index: data.index,
      nodes: data.nodes,
    }));
  }, [record?.graph_structure?.nodes]);

  return {
    record,
    phases,
    executionId: currentId,
    selectedNodeId,
    selectNode: setSelectedNodeId,
  };
}
