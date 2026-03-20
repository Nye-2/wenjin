import { useState, useCallback, useEffect, useRef } from "react";
import {
  executeWorkspaceFeature,
  getTaskStatus,
  subscribeTaskProgress,
  type TaskStatus,
} from "@/lib/api";
import { extractTaskRuntime, type TaskRuntimeState } from "@/lib/task-runtime";
import { useWorkspaceStore } from "@/stores/workspace";

export interface UseFeatureTaskRunnerOptions {
  workspaceId: string;
  featureId: string;
  runnerKey?: string;
  skipPolling?: boolean;
  refreshOnSuccess?: boolean;
  onSuccess?: (task: TaskStatus | null) => void | Promise<void>;
  onError?: () => void | Promise<void>;
}

export interface UseFeatureTaskRunnerReturn {
  run: (params: Record<string, unknown>, threadId?: string) => Promise<TaskStatus | null>;
  isRunning: boolean;
  status: string | null;
  error: string | null;
  task: TaskStatus | null;
  result: Record<string, unknown> | null;
  runtime: TaskRuntimeState | null;
  clearError: () => void;
  clearStatus: () => void;
  clearTask: () => void;
}

type RefreshTarget = "artifacts" | "papers" | "workspace";

const _VALID_REFRESH_TARGETS = new Set<RefreshTarget>([
  "artifacts",
  "papers",
  "workspace",
]);

function _resolveRefreshTargets(task: TaskStatus): RefreshTarget[] {
  const rawResult = task.result;
  if (!rawResult || typeof rawResult !== "object") {
    // Backward compatibility for legacy tasks without refresh_targets.
    return ["artifacts"];
  }

  const rawTargets = (rawResult as Record<string, unknown>).refresh_targets;
  if (!Array.isArray(rawTargets)) {
    // Backward compatibility for legacy tasks without refresh_targets.
    return ["artifacts"];
  }

  const normalized = rawTargets.filter(
    (target): target is RefreshTarget =>
      typeof target === "string" &&
      _VALID_REFRESH_TARGETS.has(target as RefreshTarget)
  );
  return [...new Set(normalized)];
}

function _resolveTaskResult(task: TaskStatus | null): Record<string, unknown> | null {
  if (!task?.result || typeof task.result !== "object") {
    return null;
  }

  const result = task.result as Record<string, unknown>;
  const nested = result.data;
  if (nested && typeof nested === "object") {
    return nested as Record<string, unknown>;
  }

  return result;
}

export function useFeatureTaskRunner({
  workspaceId,
  featureId,
  runnerKey,
  skipPolling = false,
  refreshOnSuccess = true,
  onSuccess,
  onError,
}: UseFeatureTaskRunnerOptions): UseFeatureTaskRunnerReturn {
  const [isRunning, setIsRunning] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [task, setTask] = useState<TaskStatus | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [runtime, setRuntime] = useState<TaskRuntimeState | null>(null);
  const runningRef = useRef(false);
  const taskStreamRef = useRef<(() => void) | null>(null);

  // Hold callbacks in refs so `run` never re-creates due to callback identity changes
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const { fetchArtifacts, fetchPapers, loadWorkspace } = useWorkspaceStore();
  const taskStorageKey = `feature-runner:${workspaceId}:${runnerKey || featureId}`;

  const clearError = useCallback(() => setError(null), []);
  const clearStatus = useCallback(() => setStatus(null), []);
  const persistTaskId = useCallback(
    (taskId: string) => {
      if (typeof window === "undefined") {
        return;
      }
      window.sessionStorage.setItem(taskStorageKey, taskId);
    },
    [taskStorageKey]
  );
  const clearPersistedTask = useCallback(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.sessionStorage.removeItem(taskStorageKey);
  }, [taskStorageKey]);
  const clearTask = useCallback(() => {
    setTask(null);
    setResult(null);
    setRuntime(null);
    clearPersistedTask();
  }, [clearPersistedTask]);

  useEffect(() => {
    return () => {
      taskStreamRef.current?.();
      taskStreamRef.current = null;
    };
  }, []);

  const finalizeTask = useCallback(
    async (resolvedTask: TaskStatus) => {
      setTask(resolvedTask);
      setResult(_resolveTaskResult(resolvedTask));
      const nextRuntime = extractTaskRuntime(
        resolvedTask.metadata && typeof resolvedTask.metadata === "object"
          ? (resolvedTask.metadata as Record<string, unknown>)
          : null
      );
      if (nextRuntime) {
        setRuntime(nextRuntime);
      }

      if (resolvedTask.status === "success") {
        if (refreshOnSuccess) {
          const refreshTargets = _resolveRefreshTargets(resolvedTask);
          const refreshJobs: Promise<unknown>[] = [];

          if (refreshTargets.includes("artifacts")) {
            refreshJobs.push(fetchArtifacts(workspaceId));
          }
          if (refreshTargets.includes("papers")) {
            refreshJobs.push(fetchPapers(workspaceId));
          }
          if (refreshTargets.includes("workspace")) {
            refreshJobs.push(loadWorkspace(workspaceId));
          }

          if (refreshJobs.length > 0) {
            await Promise.all(refreshJobs);
          }
        }
        setStatus(resolvedTask.message || "任务完成");
        clearPersistedTask();
        if (onSuccessRef.current) {
          await onSuccessRef.current(resolvedTask);
        }
      } else {
        setError(resolvedTask.error || resolvedTask.message || "任务执行失败");
        clearPersistedTask();
        if (onErrorRef.current) {
          await onErrorRef.current();
        }
      }
    },
    [
      refreshOnSuccess,
      fetchArtifacts,
      fetchPapers,
      loadWorkspace,
      workspaceId,
      clearPersistedTask,
    ]
  );

  const waitForTerminalTask = useCallback(
    async (taskId: string): Promise<TaskStatus | null> => {
      const task = await new Promise<TaskStatus | null>((resolve) => {
        const stopStreaming = subscribeTaskProgress(
          taskId,
          (event) => {
            if (event.message) {
              setStatus(event.message);
            }
            const nextRuntime = extractTaskRuntime(event.metadata);
            if (nextRuntime) {
              setRuntime(nextRuntime);
            }

            if (
              event.status === "success" ||
              event.status === "failed" ||
              event.status === "cancelled"
            ) {
              stopStreaming();
              taskStreamRef.current = null;
              void getTaskStatus(taskId)
                .then((finalTask) => resolve(finalTask))
                .catch(() => resolve(null));
            }
          },
          async () => {
            stopStreaming();
            taskStreamRef.current = null;
            try {
              const finalTask = await getTaskStatus(taskId);
              if (
                finalTask.status === "success" ||
                finalTask.status === "failed" ||
                finalTask.status === "cancelled"
              ) {
                resolve(finalTask);
                return;
              }
            } catch {
              // Ignore fallback fetch errors below and resolve null.
            }
            resolve(null);
          }
        );

        taskStreamRef.current?.();
        taskStreamRef.current = stopStreaming;
      });
      return task;
    },
    []
  );

  useEffect(() => {
    if (skipPolling || typeof window === "undefined" || runningRef.current) {
      return;
    }

    const persistedTaskId = window.sessionStorage.getItem(taskStorageKey);
    if (!persistedTaskId) {
      return;
    }

    let cancelled = false;

    const restoreTask = async () => {
      try {
        const currentTask = await getTaskStatus(persistedTaskId);
        if (cancelled || !currentTask) {
          return;
        }

        const restoredRuntime = extractTaskRuntime(
          currentTask.metadata && typeof currentTask.metadata === "object"
            ? (currentTask.metadata as Record<string, unknown>)
            : null
        );
        if (restoredRuntime) {
          setRuntime(restoredRuntime);
        }
        setStatus(currentTask.message || "任务恢复中...");

        if (
          currentTask.status === "success" ||
          currentTask.status === "failed" ||
          currentTask.status === "cancelled"
        ) {
          await finalizeTask(currentTask);
          return;
        }

        runningRef.current = true;
        setIsRunning(true);
        const finalTask = await waitForTerminalTask(persistedTaskId);
        if (cancelled) {
          return;
        }
        if (!finalTask) {
          setError("任务状态流中断，请稍后在工作区查看结果");
          return;
        }
        await finalizeTask(finalTask);
      } catch (error: unknown) {
        if (cancelled) {
          return;
        }
        clearPersistedTask();
        setError(
          error instanceof Error ? error.message : "任务恢复失败，请重新执行"
        );
      } finally {
        if (!cancelled) {
          setIsRunning(false);
          runningRef.current = false;
        }
      }
    };

    void restoreTask();

    return () => {
      cancelled = true;
    };
  }, [taskStorageKey, skipPolling, waitForTerminalTask, finalizeTask, clearPersistedTask]);

  const run = useCallback(
    async (params: Record<string, unknown>, threadId?: string) => {
      if (runningRef.current) return null;
      runningRef.current = true;
      setError(null);
      setStatus(null);
      clearTask();
      setIsRunning(true);

      try {
        const resp = await executeWorkspaceFeature(
          workspaceId,
          featureId,
          params,
          threadId
        );

        if (skipPolling) {
          if (resp.status === "warning") {
            setStatus(resp.message || "暂时无法执行该功能");
          } else {
            setStatus(
              resp.message || "任务已提交，稍后可在工作台查看结果。"
            );
          }
          return null;
        }

        if (resp.status === "warning" && !resp.task_id) {
          setError(resp.message || "功能暂不可用");
          if (onErrorRef.current) {
            await onErrorRef.current();
          }
          return null;
        }
        if (!resp.task_id) {
          setError("任务创建失败，请稍后重试");
          if (onErrorRef.current) {
            await onErrorRef.current();
          }
          return null;
        }

        setStatus("任务已提交，正在处理中...");
        const taskId = resp.task_id;
        persistTaskId(taskId);
        const task = await waitForTerminalTask(taskId);

        if (!task) {
          setError("任务状态流中断，请稍后在工作区查看结果");
          if (onErrorRef.current) {
            await onErrorRef.current();
          }
          return null;
        }

        await finalizeTask(task);
        return task;
      } catch (e: unknown) {
        setError(
          e instanceof Error ? e.message : "执行失败，请稍后重试"
        );
        if (onErrorRef.current) {
          await onErrorRef.current();
        }
        return null;
      } finally {
        setIsRunning(false);
        runningRef.current = false;
      }
    },
    [
      workspaceId,
      featureId,
      skipPolling,
      clearTask,
      finalizeTask,
      persistTaskId,
      waitForTerminalTask,
    ]
  );

  return {
    run,
    isRunning,
    status,
    error,
    task,
    result,
    runtime,
    clearError,
    clearStatus,
    clearTask,
  };
}
