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

const NODE_STATUSES = new Set(["pending", "running", "completed", "failed"]);

interface ExecutionState {
  /** Flat map of all known executions keyed by execution_id */
  executions: Map<string, ExecutionRecord>;
  /** Currently active execution ID (most recently updated) */
  currentExecutionId: string | null;
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
  deleteExecution: (id: string) => void;
  clear: () => void;
}

function deepCloneExecution(record: ExecutionRecord): ExecutionRecord {
  return {
    ...record,
    params: { ...record.params },
    result: record.result ? { ...record.result } : record.result,
    node_states: { ...record.node_states },
    runtime_state: record.runtime_state ? { ...record.runtime_state } : record.runtime_state,
    artifact_ids: [...record.artifact_ids],
    next_actions: record.next_actions.map((a) => ({ ...a })),
    child_execution_ids: [...record.child_execution_ids],
    graph_structure: record.graph_structure
      ? {
          ...record.graph_structure,
          nodes: record.graph_structure.nodes.map((n) => ({ ...n })),
          edges: record.graph_structure.edges.map((e) => ({ ...e })),
        }
      : record.graph_structure,
  };
}

export const useExecutionStore = create<ExecutionState>((set) => ({
  executions: new Map(),
  currentExecutionId: null,
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

        case "execution.node":
        case "execution.node.delta":
        {
          const nodeId = event.payload.node_id as string | undefined;
          if (nodeId) {
            const payloadStatus =
              typeof event.payload.status === "string" &&
              NODE_STATUSES.has(event.payload.status)
                ? event.payload.status
                : undefined;
            const nodeState: ExecutionNodeState = {
              ...(updated.node_states[nodeId] || {}),
              status: payloadStatus || updated.node_states[nodeId]?.status || "running",
            };
            if (typeof event.payload.output_preview === "string") {
              nodeState.output_preview = event.payload.output_preview;
            }
            if (typeof event.payload.thinking === "string") {
              nodeState.thinking =
                event.type === "execution.node.delta"
                  ? (nodeState.thinking || "") + event.payload.thinking
                  : event.payload.thinking;
            }
            if (event.payload.token_usage) {
              nodeState.token_usage = event.payload.token_usage as Record<string, number>;
            }
            const inputPayload = event.payload.input_data ?? event.payload.input;
            const outputPayload = event.payload.output_data ?? event.payload.output;
            if (inputPayload) {
              nodeState.input = inputPayload as Record<string, unknown>;
            }
            if (outputPayload) {
              nodeState.output = outputPayload as Record<string, unknown>;
            }
            if (Array.isArray(event.payload.tool_calls)) {
              nodeState.tool_calls = event.payload.tool_calls as Record<string, unknown>[];
            }
            if (typeof event.payload.node_type === "string") {
              nodeState.node_type = event.payload.node_type;
            }
            if (typeof event.payload.label === "string") {
              nodeState.label = event.payload.label;
            }
            if (isRecord(event.payload.node_metadata)) {
              nodeState.node_metadata = event.payload.node_metadata;
            }
            if (typeof event.payload.error === "string") {
              nodeState.error = event.payload.error;
            }
            if (typeof event.payload.started_at === "string") {
              nodeState.started_at = event.payload.started_at;
            }
            if (typeof event.payload.completed_at === "string") {
              nodeState.completed_at = event.payload.completed_at;
            }
            updated.node_states[nodeId] = nodeState;
          }
          break;
        }

        case "execution.team.invocation": {
          const invocation = isRecord(event.payload.invocation)
            ? event.payload.invocation
            : null;
          const nodeId = stringValue(invocation?.id);
          if (invocation && nodeId) {
            const nodeState: ExecutionNodeState = {
              ...(updated.node_states[nodeId] || {}),
              status: teamInvocationStatus(invocation.status),
              node_type: "agent_invocation",
              label: stringValue(invocation.display_name),
              node_metadata: {
                team: true,
                template_id: stringValue(invocation.template_id),
                display_name: stringValue(invocation.display_name),
                assigned_role: stringValue(invocation.assigned_role),
                recruitment_reason: stringValue(invocation.recruitment_reason),
                effective_tools: stringListValue(invocation.effective_tools),
                effective_skills: stringListValue(invocation.effective_skills),
              },
            };
            if (isRecord(invocation.input_brief)) {
              nodeState.input = invocation.input_brief;
            }
            if (isRecord(invocation.output_report)) {
              nodeState.output = invocation.output_report;
            }
            if (Array.isArray(invocation.tool_calls)) {
              nodeState.tool_calls = invocation.tool_calls as Record<string, unknown>[];
            }
            if (isRecord(invocation.token_usage)) {
              nodeState.token_usage = invocation.token_usage as Record<string, number>;
            }
            if (isRecord(invocation.error)) {
              nodeState.error = stringValue(invocation.error.message);
            }
            updated.node_states[nodeId] = nodeState;
          }
          break;
        }

        case "execution.team.quality_gate": {
          const gate = isRecord(event.payload.quality_gate)
            ? event.payload.quality_gate
            : null;
          if (gate) {
            updated.runtime_state = upsertQualityGate(
              updated.runtime_state,
              gate,
            );
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
      collapsedPhaseKeys: new Set(),
      collapsedExecutionIds: new Set(),
    });
  },
}));

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function stringListValue(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
}

function teamInvocationStatus(value: unknown): string {
  if (value === "succeeded") return "completed";
  if (value === "queued") return "pending";
  if (typeof value === "string" && value) return value;
  return "running";
}

function upsertQualityGate(
  runtimeState: Record<string, unknown> | null | undefined,
  gate: Record<string, unknown>,
): Record<string, unknown> {
  const gateId = stringValue(gate.gate_id) ?? stringValue(gate.id);
  const nextRuntimeState = { ...(runtimeState ?? {}) };
  const current = Array.isArray(nextRuntimeState.quality_gates)
    ? [...nextRuntimeState.quality_gates]
    : [];
  if (!gateId) {
    nextRuntimeState.quality_gates = [...current, gate];
    return nextRuntimeState;
  }
  const index = current.findIndex((item) => {
    if (!isRecord(item)) return false;
    return stringValue(item.gate_id) === gateId || stringValue(item.id) === gateId;
  });
  if (index >= 0) {
    current[index] = gate;
  } else {
    current.push(gate);
  }
  nextRuntimeState.quality_gates = current;
  return nextRuntimeState;
}
