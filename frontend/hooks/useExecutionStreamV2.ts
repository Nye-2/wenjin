import { useMemo, useState } from "react";

import { useExecutionStore } from "@/stores/execution-store";
import { useExecutionStream } from "./useExecutionStream";

export interface UseExecutionStreamV2Return {
  /** Current execution's graph nodes with resolved statuses */
  nodes: Array<{ id: string; label: string; status: string; phaseIndex?: number }>;
  /** Current execution's graph edges (mapped to source/target) */
  edges: Array<{ source: string; target: string }>;
  /** Currently selected node ID */
  selectedNodeId: string | null;
  /** Select a node (opens drawer) */
  selectNode: (id: string | null) => void;
  /** Current execution record ID, if any */
  executionId: string | null;
}

/**
 * v2 wrapper that combines the execution stream with the workspace event
 * stream for the LiveWorkflowPanel.
 */
export function useExecutionStreamV2(
  _workspaceId: string,
  executionId?: string | null,
): UseExecutionStreamV2Return {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Resolve execution ID from prop or store
  const currentId =
    executionId ?? useExecutionStore((s) => s.currentExecutionId);

  // Subscribe to execution stream using resolved ID
  useExecutionStream(currentId);

  const executions = useExecutionStore((s) => s.executions);
  const record = currentId ? executions.get(currentId) : undefined;

  // Build nodes from graph_structure + node_states, extract phaseIndex
  const nodes = useMemo(() => {
    if (!record?.graph_structure) return [];
    return record.graph_structure.nodes.map((n) => {
      const state = record.node_states[n.id];
      return {
        id: n.id,
        label: n.label ?? n.id,
        status: state?.status ?? "pending",
        phaseIndex:
          (n.metadata?.phase_index as number | undefined) ??
          (n.metadata?.phaseIndex as number | undefined) ??
          0,
      };
    });
  }, [record?.graph_structure, record?.node_states]);

  // Map edges from ExecutionGraphEdge (from/to) to source/target
  const edges = useMemo(() => {
    if (!record?.graph_structure) return [];
    return record.graph_structure.edges.map((e) => ({
      source: e.from,
      target: e.to,
    }));
  }, [record?.graph_structure]);

  return {
    nodes,
    edges,
    selectedNodeId,
    selectNode: setSelectedNodeId,
    executionId: currentId ?? null,
  };
}
