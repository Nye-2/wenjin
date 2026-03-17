import { useState, useCallback, useRef } from "react";
import { executeWorkspaceFeature, type TaskStatus } from "@/lib/api";
import { pollTaskUntilTerminal } from "@/lib/taskPolling";
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
  run: (params: Record<string, unknown>, threadId?: string) => Promise<void>;
  isRunning: boolean;
  status: string | null;
  error: string | null;
  clearError: () => void;
  clearStatus: () => void;
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

  const { fetchArtifacts, fetchPapers, loadWorkspace } = useWorkspaceStore();

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
          if (onErrorRef.current) {
            await onErrorRef.current();
          }
          return;
        }
        if (!resp.task_id) {
          setError("任务创建失败，请稍后重试");
          if (onErrorRef.current) {
            await onErrorRef.current();
          }
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
          if (onErrorRef.current) {
            await onErrorRef.current();
          }
          return;
        }

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
        } else {
          setError(task.error || task.message || "任务执行失败");
          if (onErrorRef.current) {
            await onErrorRef.current();
          }
        }
      } catch (e: unknown) {
        setError(
          e instanceof Error ? e.message : "执行失败，请稍后重试"
        );
        if (onErrorRef.current) {
          await onErrorRef.current();
        }
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
    ]
  );

  return { run, isRunning, status, error, clearError, clearStatus };
}
