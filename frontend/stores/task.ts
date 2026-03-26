// frontend/stores/task.ts

import { create } from 'zustand';
import type { FeatureStage } from '@/lib/api';

// 任务阶段状态
export interface TaskStage extends FeatureStage {
  status: 'completed' | 'running' | 'pending';
}

// 当前执行的任务
export interface CurrentTask {
  id: string;
  featureId: string;  // 对应的feature id
  status: 'running' | 'completed' | 'cancelled' | 'failed';
  agent: string;
  agentLabel: string;
  thinking: string;
  stages: TaskStage[];
  currentStageIndex: number;
  startedAt: string;
  completedAt?: string;
}

// 任务状态
interface TaskState {
  isExecuting: boolean;
  currentTask: CurrentTask | null;
  recentCompleted: CurrentTask | null;

  // Actions
  startTask: (params: {
    taskId?: string;
    featureId: string;
    agent: string;
    agentLabel: string;
    stages: FeatureStage[];
    initialThinking?: string;
  }) => string;
  syncTaskProgress: (progress: number, thinking?: string) => void;
  updateTaskThinking: (thinking: string) => void;
  advanceStage: () => void;
  completeTask: () => void;
  cancelTask: () => void;
  failTask: (error: string) => void;
  clearCurrentTask: () => void;
  clearRecentCompleted: () => void;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  isExecuting: false,
  currentTask: null,
  recentCompleted: null,

  startTask: (params) => {
    const id = params.taskId ?? `task-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
    const stagesWithStatus: TaskStage[] = params.stages.map((s, i) => ({
      ...s,
      status: i === 0 ? 'running' : 'pending',
    }));

    set({
      isExecuting: true,
      currentTask: {
        id,
        featureId: params.featureId,
        status: 'running',
        agent: params.agent,
        agentLabel: params.agentLabel,
        thinking: params.initialThinking || '',
        stages: stagesWithStatus,
        currentStageIndex: 0,
        startedAt: new Date().toISOString(),
      },
      recentCompleted: null,
    });
    return id;
  },

  syncTaskProgress: (progress, thinking) => {
    set((state) => {
      if (!state.currentTask) {
        return state;
      }

      const stageCount = state.currentTask.stages.length;
      if (stageCount === 0) {
        return {
          currentTask: {
            ...state.currentTask,
            thinking: thinking ?? state.currentTask.thinking,
          },
        };
      }

      const normalizedProgress = Math.max(0, Math.min(100, progress));
      if (normalizedProgress >= 100) {
        return {
          currentTask: {
            ...state.currentTask,
            currentStageIndex: stageCount - 1,
            thinking: thinking ?? state.currentTask.thinking,
            stages: state.currentTask.stages.map((stage) => ({
              ...stage,
              status: 'completed',
            })),
          },
        };
      }

      const currentStageIndex = Math.min(
        stageCount - 1,
        Math.floor((normalizedProgress / 100) * stageCount)
      );

      return {
        currentTask: {
          ...state.currentTask,
          currentStageIndex,
          thinking: thinking ?? state.currentTask.thinking,
          stages: state.currentTask.stages.map((stage, index) => {
            if (index < currentStageIndex) {
              return { ...stage, status: 'completed' as const };
            }
            if (index === currentStageIndex) {
              return { ...stage, status: 'running' as const };
            }
            return { ...stage, status: 'pending' as const };
          }),
        },
      };
    });
  },

  updateTaskThinking: (thinking) => {
    set((state) => ({
      currentTask: state.currentTask
        ? { ...state.currentTask, thinking }
        : null,
    }));
  },

  advanceStage: () => {
    set((state) => {
      if (!state.currentTask) return state;
      const nextIndex = state.currentTask.currentStageIndex + 1;
      const stages = state.currentTask.stages.map((s, i) => {
        if (i < nextIndex) return { ...s, status: 'completed' as const };
        if (i === nextIndex) return { ...s, status: 'running' as const };
        return { ...s, status: 'pending' as const };
      });
      return {
        currentTask: {
          ...state.currentTask,
          stages,
          currentStageIndex: nextIndex,
        },
      };
    });
  },

  completeTask: () => {
    const { currentTask } = get();
    if (!currentTask) return;

    const completedTask = {
      ...currentTask,
      status: 'completed' as const,
      completedAt: new Date().toISOString(),
      stages: currentTask.stages.map((s) => ({
        ...s,
        status: 'completed' as const,
      })),
    };

    set({
      isExecuting: false,
      currentTask: null,
      recentCompleted: completedTask,
    });

    setTimeout(() => {
      set({ recentCompleted: null });
    }, 3000);
  },

  cancelTask: () => {
    set({
      isExecuting: false,
      currentTask: null,
      recentCompleted: null,
    });
  },

  failTask: (error) => {
    set((state) => ({
      isExecuting: false,
      currentTask: state.currentTask
        ? {
            ...state.currentTask,
            status: 'failed',
            thinking: `错误: ${error}`,
            completedAt: new Date().toISOString(),
          }
        : null,
    }));
  },

  clearCurrentTask: () => {
    set({
      isExecuting: false,
      currentTask: null,
    });
  },

  clearRecentCompleted: () => {
    set({ recentCompleted: null });
  },
}));

export default useTaskStore;
