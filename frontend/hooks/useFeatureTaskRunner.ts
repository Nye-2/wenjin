import { useState, useCallback, useEffect, useRef } from "react";
import {
  executeWorkspaceFeature,
  getTaskStatus,
  subscribeTaskProgress,
  type TaskStatus,
} from "@/lib/api";
import { useWorkspaceStore } from "@/stores/workspace";

export interface UseFeatureTaskRunnerOptions {
  workspaceId: string;
  featureId: string;
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
  const runningRef = useRef(false);
  const taskStreamRef = useRef<(() => void) | null>(null);

  // Hold callbacks in refs so `run` never re-creates due to callback identity changes
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const { fetchArtifacts, fetchPapers, loadWorkspace } = useWorkspaceStore();

  const clearError = useCallback(() => setError(null), []);
  const clearStatus = useCallback(() => setStatus(null), []);
  const clearTask = useCallback(() => {
    setTask(null);
    setResult(null);
  }, []);

  useEffect(() => {
    return () => {
      taskStreamRef.current?.();
      taskStreamRef.current = null;
    };
  }, []);

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
        const task = await new Promise<TaskStatus | null>((resolve) => {
          const stopStreaming = subscribeTaskProgress(
            taskId,
            (event) => {
              if (event.message) {
                setStatus(event.message);
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

        if (!task) {
          setError("任务状态流中断，请稍后在工作区查看结果");
          if (onErrorRef.current) {
            await onErrorRef.current();
          }
          return null;
        }

        setTask(task);
        setResult(_resolveTaskResult(task));

        if (task.status === "success") {
          if (refreshOnSuccess) {
            const refreshTargets = _resolveRefreshTargets(task);
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
          setStatus(task.message || "任务完成");
          if (onSuccessRef.current) {
            await onSuccessRef.current(task);
          }
          return task;
        } else {
          setError(task.error || task.message || "任务执行失败");
          if (onErrorRef.current) {
            await onErrorRef.current();
          }
          return task;
        }
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
      refreshOnSuccess,
      fetchArtifacts,
      fetchPapers,
      loadWorkspace,
      clearTask,
    ]
  );

  return {
    run,
    isRunning,
    status,
    error,
    task,
    result,
    clearError,
    clearStatus,
    clearTask,
  };
}
