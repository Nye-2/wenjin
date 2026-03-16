import { useState, useCallback, useRef } from "react";
import { executeWorkspaceFeature, type TaskStatus } from "@/lib/api";
import { pollTaskUntilTerminal } from "@/lib/taskPolling";
import { useWorkspaceStore } from "@/stores/workspace";

export interface UseFeatureTaskRunnerOptions {
  workspaceId: string;
  featureId: string;
  skipPolling?: boolean;
  refreshOnSuccess?: boolean;
  onSuccess?: (task: TaskStatus | null) => void;
  onError?: () => void;
}

export interface UseFeatureTaskRunnerReturn {
  run: (params: Record<string, unknown>, threadId?: string) => Promise<void>;
  isRunning: boolean;
  status: string | null;
  error: string | null;
  clearError: () => void;
  clearStatus: () => void;
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
  const runningRef = useRef(false);

  // Hold callbacks in refs so `run` never re-creates due to callback identity changes
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const { fetchArtifacts } = useWorkspaceStore();

  const clearError = useCallback(() => setError(null), []);
  const clearStatus = useCallback(() => setStatus(null), []);

  const run = useCallback(
    async (params: Record<string, unknown>, threadId?: string) => {
      if (runningRef.current) return;
      runningRef.current = true;
      setError(null);
      setStatus(null);
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
          return;
        }

        if (resp.status === "warning" && !resp.task_id) {
          setError(resp.message || "功能暂不可用");
          onErrorRef.current?.();
          return;
        }
        if (!resp.task_id) {
          setError("任务创建失败，请稍后重试");
          onErrorRef.current?.();
          return;
        }

        setStatus("任务已提交，正在处理中...");
        const task = await pollTaskUntilTerminal(resp.task_id, {
          onProgress: (t) => {
            if (t.message) {
              setStatus(t.message);
            }
          },
        });

        if (!task) {
          setError("任务轮询超时，请稍后在工作区查看结果");
          onErrorRef.current?.();
          return;
        }

        if (task.status === "success") {
          if (refreshOnSuccess) {
            await fetchArtifacts(workspaceId);
          }
          setStatus(task.message || "任务完成");
          onSuccessRef.current?.(task);
        } else {
          setError(task.error || task.message || "任务执行失败");
          onErrorRef.current?.();
        }
      } catch (e: unknown) {
        setError(
          e instanceof Error ? e.message : "执行失败，请稍后重试"
        );
        onErrorRef.current?.();
      } finally {
        setIsRunning(false);
        runningRef.current = false;
      }
    },
    [workspaceId, featureId, skipPolling, refreshOnSuccess, fetchArtifacts]
  );

  return { run, isRunning, status, error, clearError, clearStatus };
}
