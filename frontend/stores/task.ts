// frontend/stores/task.ts

import { create } from "zustand";
import type { FeatureStage } from "@/lib/api";

export interface TaskStage extends FeatureStage {
  status: "completed" | "running" | "pending";
}

export interface CurrentTask {
  id: string;
  featureId: string;
  status: "running" | "completed" | "cancelled" | "failed";
  agent: string;
  agentLabel: string;
  thinking: string;
  stages: TaskStage[];
  currentStageIndex: number;
  startedAt: string;
  completedAt?: string;
}

export interface WorkspaceTaskSnapshot {
  isExecuting: boolean;
  currentTask: CurrentTask | null;
  recentCompleted: CurrentTask | null;
}

const DEFAULT_WORKSPACE_TASK_KEY = "__global__";
const EMPTY_WORKSPACE_TASK_SNAPSHOT: WorkspaceTaskSnapshot = {
  isExecuting: false,
  currentTask: null,
  recentCompleted: null,
};

function resolveWorkspaceTaskKey(workspaceId?: string | null): string {
  const normalized = (workspaceId || "").trim();
  return normalized || DEFAULT_WORKSPACE_TASK_KEY;
}

function snapshotForWorkspace(
  state: { byWorkspace: Record<string, WorkspaceTaskSnapshot> },
  workspaceId?: string | null,
): WorkspaceTaskSnapshot {
  return state.byWorkspace[resolveWorkspaceTaskKey(workspaceId)] ?? EMPTY_WORKSPACE_TASK_SNAPSHOT;
}

function withWorkspaceSnapshot(
  state: { byWorkspace: Record<string, WorkspaceTaskSnapshot> },
  workspaceId: string | null | undefined,
  snapshot: WorkspaceTaskSnapshot,
): { byWorkspace: Record<string, WorkspaceTaskSnapshot> } {
  const key = resolveWorkspaceTaskKey(workspaceId);
  return {
    byWorkspace: {
      ...state.byWorkspace,
      [key]: snapshot,
    },
  };
}

interface TaskState {
  byWorkspace: Record<string, WorkspaceTaskSnapshot>;
  getWorkspaceTaskState: (workspaceId?: string | null) => WorkspaceTaskSnapshot;
  startTask: (params: {
    workspaceId?: string | null;
    taskId?: string;
    featureId: string;
    agent: string;
    agentLabel: string;
    stages: FeatureStage[];
    initialThinking?: string;
  }) => string;
  syncTaskProgress: (params: {
    workspaceId?: string | null;
    taskId?: string | null;
    progress: number;
    thinking?: string;
  }) => void;
  updateTaskThinking: (params: {
    workspaceId?: string | null;
    taskId?: string | null;
    thinking: string;
  }) => void;
  advanceStage: (params?: {
    workspaceId?: string | null;
    taskId?: string | null;
  }) => void;
  completeTask: (params?: {
    workspaceId?: string | null;
    taskId?: string | null;
  }) => void;
  cancelTask: (params?: {
    workspaceId?: string | null;
    taskId?: string | null;
  }) => void;
  failTask: (params: {
    workspaceId?: string | null;
    taskId?: string | null;
    error: string;
  }) => void;
  clearCurrentTask: (workspaceId?: string | null) => void;
  clearRecentCompleted: (workspaceId?: string | null) => void;
  clearWorkspaceTasks: (workspaceId: string) => void;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  byWorkspace: {},

  getWorkspaceTaskState: (workspaceId) => snapshotForWorkspace(get(), workspaceId),

  startTask: (params) => {
    const id = params.taskId ?? `task-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
    const stagesWithStatus: TaskStage[] = params.stages.map((stage, index) => ({
      ...stage,
      status: index === 0 ? "running" : "pending",
    }));
    const snapshot: WorkspaceTaskSnapshot = {
      isExecuting: true,
      currentTask: {
        id,
        featureId: params.featureId,
        status: "running",
        agent: params.agent,
        agentLabel: params.agentLabel,
        thinking: params.initialThinking || "",
        stages: stagesWithStatus,
        currentStageIndex: 0,
        startedAt: new Date().toISOString(),
      },
      recentCompleted: null,
    };
    set((state) => withWorkspaceSnapshot(state, params.workspaceId, snapshot));
    return id;
  },

  syncTaskProgress: ({ workspaceId, taskId, progress, thinking }) => {
    set((state) => {
      const current = snapshotForWorkspace(state, workspaceId);
      if (!current.currentTask) {
        return state;
      }
      if (taskId && current.currentTask.id !== taskId) {
        return state;
      }

      const stageCount = current.currentTask.stages.length;
      if (stageCount === 0) {
        return withWorkspaceSnapshot(state, workspaceId, {
          ...current,
          currentTask: {
            ...current.currentTask,
            thinking: thinking ?? current.currentTask.thinking,
          },
        });
      }

      const normalizedProgress = Math.max(0, Math.min(100, progress));
      if (normalizedProgress >= 100) {
        return withWorkspaceSnapshot(state, workspaceId, {
          ...current,
          currentTask: {
            ...current.currentTask,
            currentStageIndex: stageCount - 1,
            thinking: thinking ?? current.currentTask.thinking,
            stages: current.currentTask.stages.map((stage) => ({
              ...stage,
              status: "completed",
            })),
          },
        });
      }

      const currentStageIndex = Math.min(
        stageCount - 1,
        Math.floor((normalizedProgress / 100) * stageCount)
      );

      return withWorkspaceSnapshot(state, workspaceId, {
        ...current,
        currentTask: {
          ...current.currentTask,
          currentStageIndex,
          thinking: thinking ?? current.currentTask.thinking,
          stages: current.currentTask.stages.map((stage, index) => {
            if (index < currentStageIndex) {
              return { ...stage, status: "completed" as const };
            }
            if (index === currentStageIndex) {
              return { ...stage, status: "running" as const };
            }
            return { ...stage, status: "pending" as const };
          }),
        },
      });
    });
  },

  updateTaskThinking: ({ workspaceId, taskId, thinking }) => {
    set((state) => {
      const current = snapshotForWorkspace(state, workspaceId);
      if (!current.currentTask) {
        return state;
      }
      if (taskId && current.currentTask.id !== taskId) {
        return state;
      }
      return withWorkspaceSnapshot(state, workspaceId, {
        ...current,
        currentTask: {
          ...current.currentTask,
          thinking,
        },
      });
    });
  },

  advanceStage: ({ workspaceId, taskId } = {}) => {
    set((state) => {
      const current = snapshotForWorkspace(state, workspaceId);
      if (!current.currentTask) {
        return state;
      }
      if (taskId && current.currentTask.id !== taskId) {
        return state;
      }
      const nextIndex = current.currentTask.currentStageIndex + 1;
      const stages = current.currentTask.stages.map((stage, index) => {
        if (index < nextIndex) {
          return { ...stage, status: "completed" as const };
        }
        if (index === nextIndex) {
          return { ...stage, status: "running" as const };
        }
        return { ...stage, status: "pending" as const };
      });
      return withWorkspaceSnapshot(state, workspaceId, {
        ...current,
        currentTask: {
          ...current.currentTask,
          stages,
          currentStageIndex: nextIndex,
        },
      });
    });
  },

  completeTask: ({ workspaceId, taskId } = {}) => {
    const completionAt = new Date().toISOString();
    const completedTaskId = (() => {
      const snapshot = get().getWorkspaceTaskState(workspaceId);
      if (!snapshot.currentTask) {
        return null;
      }
      if (taskId && snapshot.currentTask.id !== taskId) {
        return null;
      }
      const completedTask: CurrentTask = {
        ...snapshot.currentTask,
        status: "completed",
        completedAt: completionAt,
        stages: snapshot.currentTask.stages.map((stage) => ({
          ...stage,
          status: "completed",
        })),
      };
      set((state) =>
        withWorkspaceSnapshot(state, workspaceId, {
          isExecuting: false,
          currentTask: null,
          recentCompleted: completedTask,
        })
      );
      return completedTask.id;
    })();

    if (!completedTaskId) {
      return;
    }

    setTimeout(() => {
      set((state) => {
        const current = snapshotForWorkspace(state, workspaceId);
        if (current.recentCompleted?.id !== completedTaskId) {
          return state;
        }
        return withWorkspaceSnapshot(state, workspaceId, {
          ...current,
          recentCompleted: null,
        });
      });
    }, 3000);
  },

  cancelTask: ({ workspaceId, taskId } = {}) => {
    set((state) => {
      const current = snapshotForWorkspace(state, workspaceId);
      if (taskId && current.currentTask?.id !== taskId) {
        return state;
      }
      return withWorkspaceSnapshot(state, workspaceId, {
        isExecuting: false,
        currentTask: null,
        recentCompleted: null,
      });
    });
  },

  failTask: ({ workspaceId, taskId, error }) => {
    set((state) => {
      const current = snapshotForWorkspace(state, workspaceId);
      if (!current.currentTask) {
        return state;
      }
      if (taskId && current.currentTask.id !== taskId) {
        return state;
      }
      return withWorkspaceSnapshot(state, workspaceId, {
        ...current,
        isExecuting: false,
        currentTask: {
          ...current.currentTask,
          status: "failed",
          thinking: `错误: ${error}`,
          completedAt: new Date().toISOString(),
        },
      });
    });
  },

  clearCurrentTask: (workspaceId) => {
    set((state) => {
      const current = snapshotForWorkspace(state, workspaceId);
      return withWorkspaceSnapshot(state, workspaceId, {
        ...current,
        isExecuting: false,
        currentTask: null,
      });
    });
  },

  clearRecentCompleted: (workspaceId) => {
    set((state) => {
      const current = snapshotForWorkspace(state, workspaceId);
      return withWorkspaceSnapshot(state, workspaceId, {
        ...current,
        recentCompleted: null,
      });
    });
  },

  clearWorkspaceTasks: (workspaceId) => {
    set((state) => {
      const key = resolveWorkspaceTaskKey(workspaceId);
      if (!(key in state.byWorkspace)) {
        return state;
      }
      const next = { ...state.byWorkspace };
      delete next[key];
      return { byWorkspace: next };
    });
  },
}));

export default useTaskStore;
