/**
 * Execution store — consumes `ExecutionStreamEvent` from SSE and maintains
 * a flat map of `ExecutionRecord` objects.
 */
import { create } from "zustand";

import type {
  ExecutionRecord,
  ExecutionStreamEvent,
  ExecutionNodeState,
  ExecutionStatus,
} from "@/lib/api/types";

const TERMINAL_EXECUTION_STATUSES = new Set<ExecutionStatus>([
  "completed",
  "failed_partial",
  "failed",
  "cancelled",
]);

interface ExecutionState {
  /** Flat map of all known executions keyed by execution_id */
  executions: Map<string, ExecutionRecord>;
  /** Currently active execution ID (most recently updated) */
  currentExecutionId: string | null;
  /** Set of execution IDs that the user has explicitly paused */
  pausedExecutionIds: Set<string>;
  /** Collapsed phase keys for UI state */
  collapsedPhaseKeys: Set<string>;
  /** Collapsed execution IDs for UI state */
  collapsedExecutionIds: Set<string>;

  // Actions
  upsertExecution: (record: ExecutionRecord) => void;
  applyStreamEvent: (event: ExecutionStreamEvent) => void;
  setCurrentExecution: (id: string | null) => void;
  toggleExecutionCollapsed: (id: string) => void;
  togglePhaseCollapsed: (executionId: string, phaseIndex: number) => void;
  pauseExecution: (id: string) => void;
  resumeExecution: (id: string) => void;
  deleteExecution: (id: string) => void;
  clear: () => void;
}

function deepCloneExecution(record: ExecutionRecord): ExecutionRecord {
  return {
    ...record,
    params: { ...record.params },
    result: record.result ? { ...record.result } : record.result,
    node_states: { ...record.node_states },
    artifact_ids: [...record.artifact_ids],
    next_actions: record.next_actions.map((a) => ({ ...a })),
    child_execution_ids: [...record.child_execution_ids],
    graph_structure: record.graph_structure
      ? {
          nodes: record.graph_structure.nodes.map((n) => ({ ...n })),
          edges: record.graph_structure.edges.map((e) => ({ ...e })),
        }
      : record.graph_structure,
  };
}

export const useExecutionStore = create<ExecutionState>((set, get) => ({
  executions: new Map(),
  currentExecutionId: null,
  pausedExecutionIds: new Set(),
  collapsedPhaseKeys: new Set(),
  collapsedExecutionIds: new Set(),

  upsertExecution(record) {
    set((state) => {
      const next = new Map(state.executions);
      next.set(record.id, deepCloneExecution(record));
      return {
        executions: next,
        currentExecutionId: record.id,
      };
    });
  },

  applyStreamEvent(event) {
    set((state) => {
      const record = state.executions.get(event.execution_id);
      if (!record) {
        // Stream event arrived before metadata — create a placeholder
        const placeholder: ExecutionRecord = {
          id: event.execution_id,
          user_id: "",
          execution_type: "feature",
          status: "running",
          params: {},
          node_states: {},
          artifact_ids: [],
          next_actions: [],
          child_execution_ids: [],
          progress: 0,
          created_at: event.timestamp,
          updated_at: event.timestamp,
        };
        const next = new Map(state.executions);
        next.set(event.execution_id, placeholder);
        return {
          executions: next,
          currentExecutionId: event.execution_id,
        };
      }

      const updated = deepCloneExecution(record);
      updated.updated_at = event.timestamp;

      switch (event.type) {
        case "execution.metadata": {
          const p = event.payload;
          if (typeof p.execution_type === "string") {
            updated.execution_type = p.execution_type as ExecutionRecord["execution_type"];
          }
          if (typeof p.status === "string") {
            updated.status = p.status as ExecutionRecord["status"];
          }
          if (typeof p.workspace_id === "string") updated.workspace_id = p.workspace_id;
          if (typeof p.thread_id === "string") updated.thread_id = p.thread_id;
          if (typeof p.feature_id === "string") updated.feature_id = p.feature_id;
          if (typeof p.message === "string") updated.message = p.message;
          if (typeof p.progress === "number") updated.progress = p.progress;
          break;
        }

        case "execution.graph_structure": {
          if (event.payload.graph_structure) {
            updated.graph_structure = event.payload.graph_structure as ExecutionRecord["graph_structure"];
          }
          break;
        }

        case "execution.node.started":
        case "execution.node.delta":
        case "execution.node.completed":
        case "execution.node.failed": {
          const nodeId = event.payload.node_id as string | undefined;
          if (nodeId) {
            const nodeState: ExecutionNodeState = {
              ...(updated.node_states[nodeId] || {}),
              status: event.type === "execution.node.started"
                ? "running"
                : event.type === "execution.node.completed"
                  ? "completed"
                  : event.type === "execution.node.failed"
                    ? "failed"
                    : updated.node_states[nodeId]?.status || "running",
            };
            if (typeof event.payload.output_preview === "string") {
              nodeState.output_preview = event.payload.output_preview;
            }
            if (typeof event.payload.thinking === "string") {
              nodeState.thinking = (nodeState.thinking || "") + event.payload.thinking;
            }
            if (event.payload.token_usage) {
              nodeState.token_usage = event.payload.token_usage as Record<string, number>;
            }
            if (event.payload.input_data) {
              nodeState.input = event.payload.input_data as Record<string, unknown>;
            }
            if (event.payload.output_data) {
              nodeState.output = event.payload.output_data as Record<string, unknown>;
            }
            updated.node_states[nodeId] = nodeState;
          }
          break;
        }

        case "execution.status": {
          if (typeof event.payload.status === "string") {
            updated.status = event.payload.status as ExecutionRecord["status"];
          }
          if (typeof event.payload.progress === "number") {
            updated.progress = event.payload.progress;
          }
          if (typeof event.payload.message === "string") {
            updated.message = event.payload.message;
          }
          break;
        }

        case "execution.completed": {
          updated.status =
            (event.payload.status as ExecutionStatus | undefined) || "completed";
          if (event.payload.result) {
            updated.result = event.payload.result as Record<string, unknown>;
          } else {
            updated.result = event.payload;
          }
          if (typeof event.payload.result_summary === "string") {
            updated.result_summary = event.payload.result_summary;
          } else if (typeof event.payload.narrative === "string") {
            updated.result_summary = event.payload.narrative;
          }
          updated.completed_at = event.timestamp;
          break;
        }

        case "execution.error": {
          updated.status = "failed";
          if (typeof event.payload.error === "string") {
            updated.error = event.payload.error;
            updated.last_error = event.payload.error;
          }
          updated.completed_at = event.timestamp;
          break;
        }

        case "execution.end": {
          // Terminal sentinel — ensure status is terminal
          if (!TERMINAL_EXECUTION_STATUSES.has(updated.status)) {
            updated.status = "completed";
          }
          if (!updated.completed_at) {
            updated.completed_at = event.timestamp;
          }
          break;
        }
      }

      const next = new Map(state.executions);
      next.set(event.execution_id, updated);
      return {
        executions: next,
        currentExecutionId: event.execution_id,
      };
    });
  },

  setCurrentExecution(id) {
    set({ currentExecutionId: id });
  },

  toggleExecutionCollapsed(id) {
    set((state) => {
      const next = new Set(state.collapsedExecutionIds);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { collapsedExecutionIds: next };
    });
  },

  togglePhaseCollapsed(executionId, phaseIndex) {
    const key = `${executionId}:${phaseIndex}`;
    set((state) => {
      const next = new Set(state.collapsedPhaseKeys);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return { collapsedPhaseKeys: next };
    });
  },

  pauseExecution(id) {
    set((state) => ({
      pausedExecutionIds: new Set([...state.pausedExecutionIds, id]),
    }));
  },

  resumeExecution(id) {
    set((state) => {
      const next = new Set(state.pausedExecutionIds);
      next.delete(id);
      return { pausedExecutionIds: next };
    });
  },

  deleteExecution(id) {
    set((state) => {
      const next = new Map(state.executions);
      next.delete(id);
      return {
        executions: next,
        currentExecutionId:
          state.currentExecutionId === id ? null : state.currentExecutionId,
      };
    });
  },

  clear() {
    set({
      executions: new Map(),
      currentExecutionId: null,
      pausedExecutionIds: new Set(),
      collapsedPhaseKeys: new Set(),
      collapsedExecutionIds: new Set(),
    });
  },
}));
