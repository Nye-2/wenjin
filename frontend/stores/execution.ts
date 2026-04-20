import { create } from "zustand";

import {
  getWorkspaceExecutionSessions,
  type ExecutionSession,
  type TokenUsageCounter,
  type WorkspaceSubagentUpdatedEvent,
  type WorkspaceTaskEvent,
} from "@/lib/api";

interface ExecutionStoreState {
  byWorkspace: Record<string, ExecutionSession[]>;
  isLoadingByWorkspace: Record<string, boolean>;
  activeExecutionIdByWorkspace: Record<string, string | null>;
  dismissedExecutionIdsByWorkspace: Record<string, string[]>;
  hydrateWorkspace: (workspaceId: string, limit?: number) => Promise<void>;
  upsertExecution: (workspaceId: string, execution: ExecutionSession) => void;
  ingestTaskEvent: (
    workspaceId: string,
    task: WorkspaceTaskEvent["task"],
    timestamp?: string
  ) => boolean;
  appendSubagentUpdate: (
    workspaceId: string,
    event: WorkspaceSubagentUpdatedEvent
  ) => boolean;
  setActiveExecution: (workspaceId: string, executionId: string | null) => void;
  dismissExecution: (workspaceId: string, executionId: string) => void;
  clearWorkspace: (workspaceId: string) => void;
}

function readTokenCounter(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.max(0, Math.trunc(value));
  }
  if (typeof value === "string") {
    const parsed = Number.parseInt(value.trim(), 10);
    if (Number.isFinite(parsed)) {
      return Math.max(0, parsed);
    }
  }
  return 0;
}

function parseTokenUsage(value: unknown): TokenUsageCounter | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  const input = readTokenCounter(candidate.input_tokens);
  const output = readTokenCounter(candidate.output_tokens);
  const explicitTotal = readTokenCounter(candidate.total_tokens);
  const total = explicitTotal > 0 ? explicitTotal : input + output;
  if (input <= 0 && output <= 0 && total <= 0) {
    return null;
  }
  return {
    input_tokens: input,
    output_tokens: output,
    total_tokens: total,
  };
}

function aggregateSubagentTokenUsage(
  subagents: ExecutionSession["subagents"] | undefined
): TokenUsageCounter | null {
  if (!Array.isArray(subagents) || subagents.length === 0) {
    return null;
  }
  let input = 0;
  let output = 0;
  let total = 0;
  for (const subagent of subagents) {
    const usage = parseTokenUsage(subagent?.token_usage);
    if (!usage) {
      continue;
    }
    input += usage.input_tokens;
    output += usage.output_tokens;
    total += usage.total_tokens;
  }
  if (input <= 0 && output <= 0 && total <= 0) {
    return null;
  }
  return {
    input_tokens: input,
    output_tokens: output,
    total_tokens: total,
  };
}

function isSameTokenUsage(
  left: TokenUsageCounter | null | undefined,
  right: TokenUsageCounter | null | undefined
): boolean {
  if (!left && !right) {
    return true;
  }
  if (!left || !right) {
    return false;
  }
  return (
    left.input_tokens === right.input_tokens &&
    left.output_tokens === right.output_tokens &&
    left.total_tokens === right.total_tokens
  );
}

function normalizeExecution(
  execution: ExecutionSession,
  previous?: ExecutionSession | null
): ExecutionSession {
  const tokenUsage =
    parseTokenUsage(execution.token_usage) ??
    aggregateSubagentTokenUsage(execution.subagents) ??
    previous?.token_usage ??
    null;
  return {
    ...previous,
    ...execution,
    task_ids: execution.task_ids,
    artifact_ids: execution.artifact_ids,
    next_actions: execution.next_actions,
    progress: execution.progress ?? previous?.progress ?? null,
    task_message: execution.task_message ?? previous?.task_message ?? null,
    current_step: execution.current_step ?? previous?.current_step ?? null,
    result_payload: execution.result_payload ?? previous?.result_payload ?? null,
    subagents: execution.subagents ?? previous?.subagents ?? [],
    token_usage: tokenUsage,
  };
}

function upsertExecutionList(
  items: ExecutionSession[],
  execution: ExecutionSession
): ExecutionSession[] {
  const existing = items.find((item) => item.id === execution.id);
  const nextExecution = normalizeExecution(execution, existing);
  if (
    existing &&
    existing.status === nextExecution.status &&
    existing.updated_at === nextExecution.updated_at &&
    existing.primary_task_id === nextExecution.primary_task_id &&
    existing.result_summary === nextExecution.result_summary &&
    existing.last_error === nextExecution.last_error &&
    existing.progress === nextExecution.progress &&
    existing.task_message === nextExecution.task_message &&
    existing.current_step === nextExecution.current_step &&
    existing.runtime_snapshot === nextExecution.runtime_snapshot &&
    existing.result_payload === nextExecution.result_payload &&
    existing.subagents === nextExecution.subagents &&
    isSameTokenUsage(existing.token_usage, nextExecution.token_usage)
  ) {
    return items;
  }

  const next = [nextExecution, ...items.filter((item) => item.id !== nextExecution.id)];
  next.sort((left, right) =>
    String(right.updated_at || right.created_at || "").localeCompare(
      String(left.updated_at || left.created_at || "")
    )
  );
  return next;
}

function selectPreferredExecutionId(items: ExecutionSession[]): string | null {
  const active = items.find(
    (item) =>
      item.status === "running" ||
      item.status === "pending" ||
      item.status === "awaiting_user_input"
  );
  return active?.id ?? items[0]?.id ?? null;
}

function resolveActiveExecutionId(
  items: ExecutionSession[],
  currentActiveExecutionId: string | null,
  dismissedExecutionIds: string[]
): string | null {
  const visible = items.filter((item) => !dismissedExecutionIds.includes(item.id));
  if (
    currentActiveExecutionId &&
    visible.some((item) => item.id === currentActiveExecutionId)
  ) {
    return currentActiveExecutionId;
  }
  return selectPreferredExecutionId(visible);
}

function mergeTaskIntoExecution(
  execution: ExecutionSession,
  task: WorkspaceTaskEvent["task"],
  timestamp?: string
): ExecutionSession {
  const taskTokenUsage = parseTokenUsage(task.metadata?.token_usage);
  const normalizedStatus = normalizeTaskStatusToExecutionStatus(
    task.status,
    execution.status
  );
  return normalizeExecution(
    {
      ...execution,
      status: normalizedStatus,
      primary_task_id: execution.primary_task_id ?? task.task_id,
      task_ids: execution.task_ids.includes(task.task_id)
        ? execution.task_ids
        : [...execution.task_ids, task.task_id],
      runtime_snapshot:
        (task.metadata?.runtime as Record<string, unknown> | undefined) ??
        execution.runtime_snapshot,
      progress:
        typeof task.progress === "number" ? task.progress : execution.progress ?? null,
      task_message: task.message ?? execution.task_message ?? null,
      current_step: task.current_step ?? execution.current_step ?? null,
      result_payload: task.result ?? execution.result_payload ?? null,
      token_usage: taskTokenUsage ?? execution.token_usage ?? null,
      result_summary:
        task.message ?? execution.result_summary ?? execution.launch_message ?? null,
      last_error: task.error ?? execution.last_error ?? null,
      updated_at: timestamp ?? new Date().toISOString(),
    },
    execution
  );
}

function findExecutionForTaskEvent(
  items: ExecutionSession[],
  task: WorkspaceTaskEvent["task"]
): ExecutionSession | null {
  const executionSessionId =
    typeof task.execution_session_id === "string"
      ? task.execution_session_id.trim()
      : "";
  if (executionSessionId) {
    const direct = items.find((item) => item.id === executionSessionId);
    if (direct) {
      return direct;
    }
  }

  const taskId =
    typeof task.task_id === "string"
      ? task.task_id.trim()
      : "";
  if (!taskId) {
    return null;
  }

  return (
    items.find((item) => item.primary_task_id === taskId) ??
    items.find((item) => item.task_ids.includes(taskId)) ??
    null
  );
}

function normalizeTaskStatusToExecutionStatus(
  taskStatus: string,
  fallbackStatus: string
): string {
  switch (taskStatus) {
    case "success":
      return "completed";
    case "failed":
      return "failed";
    case "cancelled":
      return "cancelled";
    case "running":
      return "running";
    case "pending":
      return "pending";
    default:
      return fallbackStatus;
  }
}

function normalizeWorkflowIndex(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.max(0, Math.trunc(value));
  }
  if (typeof value === "string") {
    const parsed = Number.parseInt(value.trim(), 10);
    if (Number.isFinite(parsed)) {
      return Math.max(0, parsed);
    }
  }
  return null;
}

function selectSubagentExecution(
  executions: ExecutionSession[],
  _activeExecutionId: string | null,
  event: WorkspaceSubagentUpdatedEvent
): ExecutionSession | null {
  const directExecutionSessionId =
    event.subagent.execution_session_id.trim();
  return (
    executions.find((execution) => execution.id === directExecutionSessionId) ??
    null
  );
}

export const useExecutionStore = create<ExecutionStoreState>((set) => ({
  byWorkspace: {},
  isLoadingByWorkspace: {},
  activeExecutionIdByWorkspace: {},
  dismissedExecutionIdsByWorkspace: {},

  hydrateWorkspace: async (workspaceId, limit = 20) => {
    set((state) => ({
      isLoadingByWorkspace: {
        ...state.isLoadingByWorkspace,
        [workspaceId]: true,
      },
    }));

    try {
      const response = await getWorkspaceExecutionSessions(workspaceId, limit);
      set((state) => {
        const dismissedExecutionIds =
          state.dismissedExecutionIdsByWorkspace[workspaceId] ?? [];
        const items = response.items.map((item) => normalizeExecution(item));
        return {
          byWorkspace: {
            ...state.byWorkspace,
            [workspaceId]: items,
          },
          isLoadingByWorkspace: {
            ...state.isLoadingByWorkspace,
            [workspaceId]: false,
          },
          activeExecutionIdByWorkspace: {
            ...state.activeExecutionIdByWorkspace,
            [workspaceId]: resolveActiveExecutionId(
              items,
              state.activeExecutionIdByWorkspace[workspaceId] ?? null,
              dismissedExecutionIds
            ),
          },
        };
      });
    } catch {
      set((state) => ({
        isLoadingByWorkspace: {
          ...state.isLoadingByWorkspace,
          [workspaceId]: false,
        },
      }));
    }
  },

  upsertExecution: (workspaceId, execution) => {
    set((state) => {
      const items = upsertExecutionList(
        state.byWorkspace[workspaceId] ?? [],
        execution
      );
      const dismissedExecutionIds =
        state.dismissedExecutionIdsByWorkspace[workspaceId] ?? [];
      const shouldRestoreDismissedExecution =
        (execution.status === "running" ||
          execution.status === "pending" ||
          execution.status === "awaiting_user_input") &&
        dismissedExecutionIds.includes(execution.id);
      const nextDismissedExecutionIds = shouldRestoreDismissedExecution
        ? dismissedExecutionIds.filter((item) => item !== execution.id)
        : dismissedExecutionIds;
      return {
        byWorkspace: {
          ...state.byWorkspace,
          [workspaceId]: items,
        },
        dismissedExecutionIdsByWorkspace: {
          ...state.dismissedExecutionIdsByWorkspace,
          [workspaceId]: nextDismissedExecutionIds,
        },
        activeExecutionIdByWorkspace: {
          ...state.activeExecutionIdByWorkspace,
          [workspaceId]: resolveActiveExecutionId(
            items,
            state.activeExecutionIdByWorkspace[workspaceId] ?? null,
            nextDismissedExecutionIds
          ),
        },
      };
    });
  },

  ingestTaskEvent: (workspaceId, task, timestamp) => {
    let applied = false;
    set((state) => {
      const items = state.byWorkspace[workspaceId] ?? [];
      const existing = findExecutionForTaskEvent(items, task);
      if (!existing) {
        return state;
      }
      applied = true;

      const nextExecution = mergeTaskIntoExecution(existing, task, timestamp);
      const nextItems = upsertExecutionList(items, nextExecution);
      const dismissedExecutionIds =
        state.dismissedExecutionIdsByWorkspace[workspaceId] ?? [];
      return {
        byWorkspace: {
          ...state.byWorkspace,
          [workspaceId]: nextItems,
        },
        activeExecutionIdByWorkspace: {
          ...state.activeExecutionIdByWorkspace,
          [workspaceId]: resolveActiveExecutionId(
            nextItems,
            state.activeExecutionIdByWorkspace[workspaceId] ?? null,
            dismissedExecutionIds
          ),
        },
      };
    });
    return applied;
  },

  appendSubagentUpdate: (workspaceId, event) => {
    if (!event.subagent.execution_session_id) {
      return false;
    }

    let applied = false;
    set((state) => {
      const items = state.byWorkspace[workspaceId] ?? [];
      const target = selectSubagentExecution(
        items,
        state.activeExecutionIdByWorkspace[workspaceId] ?? null,
        event
      );
      if (!target) {
        return state;
      }
      applied = true;

      const nextSubagent = {
        task_id: event.subagent.task_id,
        thread_id: event.subagent.thread_id,
        execution_session_id: event.subagent.execution_session_id,
        status: event.subagent.status,
        subagent_type:
          typeof event.subagent.subagent_type === "string"
            ? event.subagent.subagent_type
            : null,
        workflow_phase:
          typeof event.subagent.workflow_phase === "string"
            ? event.subagent.workflow_phase
            : null,
        workflow_phase_index: normalizeWorkflowIndex(
          event.subagent.workflow_phase_index
        ),
        workflow_task_index: normalizeWorkflowIndex(
          event.subagent.workflow_task_index
        ),
        workflow_strategy:
          typeof event.subagent.workflow_strategy === "string"
            ? event.subagent.workflow_strategy
            : null,
        output_preview:
          typeof event.subagent.output_preview === "string"
            ? event.subagent.output_preview
            : null,
        error:
          typeof event.subagent.error === "string"
            ? event.subagent.error
            : null,
        token_usage: parseTokenUsage(event.subagent.token_usage),
        model_name:
          typeof event.subagent.model_name === "string"
            ? event.subagent.model_name
            : null,
        updated_at: event.timestamp ?? new Date().toISOString(),
      };

      const currentSubagents = target.subagents ?? [];
      const existing = currentSubagents.find(
        (item) => item.task_id === nextSubagent.task_id
      );
      if (
        existing &&
        existing.status === nextSubagent.status &&
        existing.execution_session_id === nextSubagent.execution_session_id &&
        existing.subagent_type === nextSubagent.subagent_type &&
        existing.workflow_phase === nextSubagent.workflow_phase &&
        existing.workflow_phase_index === nextSubagent.workflow_phase_index &&
        existing.workflow_task_index === nextSubagent.workflow_task_index &&
        existing.workflow_strategy === nextSubagent.workflow_strategy &&
        existing.output_preview === nextSubagent.output_preview &&
        existing.error === nextSubagent.error &&
        isSameTokenUsage(existing.token_usage, nextSubagent.token_usage) &&
        existing.model_name === nextSubagent.model_name &&
        existing.updated_at === nextSubagent.updated_at
      ) {
        return state;
      }

      const nextSubagents = [
        nextSubagent,
        ...currentSubagents.filter(
          (item) => item.task_id !== nextSubagent.task_id
        ),
      ].slice(0, 16);
      const nextTokenUsage = aggregateSubagentTokenUsage(nextSubagents);
      const nextExecution = normalizeExecution(
        {
          ...target,
          subagents: nextSubagents,
          token_usage: nextTokenUsage ?? target.token_usage ?? null,
          updated_at: nextSubagent.updated_at,
        },
        target
      );
      return {
        byWorkspace: {
          ...state.byWorkspace,
          [workspaceId]: upsertExecutionList(items, nextExecution),
        },
      };
    });
    return applied;
  },

  setActiveExecution: (workspaceId, executionId) => {
    set((state) => ({
      activeExecutionIdByWorkspace: {
        ...state.activeExecutionIdByWorkspace,
        [workspaceId]: executionId,
      },
    }));
  },

  dismissExecution: (workspaceId, executionId) => {
    set((state) => {
      const currentDismissedExecutionIds =
        state.dismissedExecutionIdsByWorkspace[workspaceId] ?? [];
      const nextDismissedExecutionIds = currentDismissedExecutionIds.includes(executionId)
        ? currentDismissedExecutionIds
        : [...currentDismissedExecutionIds, executionId];
      const items = state.byWorkspace[workspaceId] ?? [];
      return {
        dismissedExecutionIdsByWorkspace: {
          ...state.dismissedExecutionIdsByWorkspace,
          [workspaceId]: nextDismissedExecutionIds,
        },
        activeExecutionIdByWorkspace: {
          ...state.activeExecutionIdByWorkspace,
          [workspaceId]: resolveActiveExecutionId(
            items,
            state.activeExecutionIdByWorkspace[workspaceId] ?? null,
            nextDismissedExecutionIds
          ),
        },
      };
    });
  },

  clearWorkspace: (workspaceId) => {
    set((state) => {
      const nextExecutions = { ...state.byWorkspace };
      const nextLoading = { ...state.isLoadingByWorkspace };
      const nextActive = { ...state.activeExecutionIdByWorkspace };
      const nextDismissed = { ...state.dismissedExecutionIdsByWorkspace };
      delete nextExecutions[workspaceId];
      delete nextLoading[workspaceId];
      delete nextActive[workspaceId];
      delete nextDismissed[workspaceId];
      return {
        byWorkspace: nextExecutions,
        isLoadingByWorkspace: nextLoading,
        activeExecutionIdByWorkspace: nextActive,
        dismissedExecutionIdsByWorkspace: nextDismissed,
      };
    });
  },
}));
