import { create } from "zustand";

import {
  getWorkspaceExecutionSessions,
  type ExecutionSession,
} from "@/lib/api";

interface ExecutionStoreState {
  byWorkspace: Record<string, ExecutionSession[]>;
  isLoadingByWorkspace: Record<string, boolean>;
  activeExecutionIdByWorkspace: Record<string, string | null>;
  dismissedExecutionIdsByWorkspace: Record<string, string[]>;
  hydrateWorkspace: (workspaceId: string, limit?: number) => Promise<void>;
  upsertExecution: (workspaceId: string, execution: ExecutionSession) => void;
  setActiveExecution: (workspaceId: string, executionId: string | null) => void;
  dismissExecution: (workspaceId: string, executionId: string) => void;
  clearWorkspace: (workspaceId: string) => void;
}

function upsertExecutionList(
  items: ExecutionSession[],
  execution: ExecutionSession
): ExecutionSession[] {
  const existing = items.find((item) => item.id === execution.id);
  const merged: ExecutionSession = existing
    ? {
        ...existing,
        ...execution,
        subagents: execution.subagents ?? existing.subagents ?? [],
        token_usage: execution.token_usage ?? existing.token_usage ?? null,
        progress: execution.progress ?? existing.progress ?? null,
        task_message: execution.task_message ?? existing.task_message ?? null,
        current_step: execution.current_step ?? existing.current_step ?? null,
        result_payload: execution.result_payload ?? existing.result_payload ?? null,
      }
    : execution;

  const isSameObject = <T>(left: T, right: T): boolean =>
    JSON.stringify(left) === JSON.stringify(right);

  if (
    existing &&
    existing.status === merged.status &&
    existing.updated_at === merged.updated_at &&
    existing.primary_task_id === merged.primary_task_id &&
    existing.result_summary === merged.result_summary &&
    existing.last_error === merged.last_error &&
    existing.progress === merged.progress &&
    existing.task_message === merged.task_message &&
    existing.current_step === merged.current_step &&
    isSameObject(existing.runtime_snapshot, merged.runtime_snapshot) &&
    isSameObject(existing.result_payload, merged.result_payload) &&
    isSameObject(existing.subagents, merged.subagents) &&
    isSameObject(existing.token_usage, merged.token_usage)
  ) {
    return items;
  }

  const next = [merged, ...items.filter((item) => item.id !== merged.id)];
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
        return {
          byWorkspace: {
            ...state.byWorkspace,
            [workspaceId]: response.items,
          },
          isLoadingByWorkspace: {
            ...state.isLoadingByWorkspace,
            [workspaceId]: false,
          },
          activeExecutionIdByWorkspace: {
            ...state.activeExecutionIdByWorkspace,
            [workspaceId]: resolveActiveExecutionId(
              response.items,
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
