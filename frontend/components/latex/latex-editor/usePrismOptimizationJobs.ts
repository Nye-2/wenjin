import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ExecutionRecord } from "@/lib/api";
import { listExecutions } from "@/lib/api/executions";
import { groupExecutionPhases } from "@/lib/execution-phases";
import {
  jobStatusFromExecution,
  TERMINAL_PRISM_EXECUTION_STATUSES,
  type PrismOptimizationJob,
} from "./prismOptimizationJobs";

interface UsePrismOptimizationJobsOptions {
  workspaceId?: string;
  projectId: string;
  executions: Map<string, ExecutionRecord>;
  upsertExecution: (record: ExecutionRecord) => void;
  loadProject: (projectId: string) => Promise<void>;
  onReviewStateChanged?: () => void;
  onFeedbackStatus: (message: string) => void;
}

export function usePrismOptimizationJobs({
  workspaceId,
  projectId,
  executions,
  upsertExecution,
  loadProject,
  onReviewStateChanged,
  onFeedbackStatus,
}: UsePrismOptimizationJobsOptions) {
  const [jobs, setJobs] = useState<PrismOptimizationJob[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [isTraceOpen, setTraceOpen] = useState(false);
  const syncedExecutionsRef = useRef<Set<string>>(new Set());

  const projectedJobs = useMemo(
    () =>
      jobs.map((job) => {
        const record = job.executionId ? executions.get(job.executionId) : null;
        const status = jobStatusFromExecution(record);
        return status && status !== job.status ? { ...job, status } : job;
      }),
    [executions, jobs],
  );

  const executionIds = useMemo(
    () =>
      projectedJobs
        .map((job) => job.executionId?.trim())
        .filter((id): id is string => Boolean(id)),
    [projectedJobs],
  );
  const executionIdKey = executionIds.join("|");

  const activeJob = useMemo(() => {
    if (!projectedJobs.length) {
      return null;
    }
    if (activeJobId) {
      const active = projectedJobs.find((job) => job.id === activeJobId);
      if (active) {
        return active;
      }
    }
    return projectedJobs[0];
  }, [activeJobId, projectedJobs]);

  const activeRecord = useMemo(() => {
    if (!activeJob?.executionId) {
      return null;
    }
    return executions.get(activeJob.executionId) ?? null;
  }, [activeJob, executions]);

  const activePhases = useMemo(
    () => groupExecutionPhases(activeRecord),
    [activeRecord],
  );

  const records = useMemo(
    () =>
      projectedJobs
        .map((job) => (job.executionId ? executions.get(job.executionId) : null))
        .filter((record): record is ExecutionRecord => Boolean(record)),
    [executions, projectedJobs],
  );

  const optimizingFeedbackIds = useMemo(() => {
    const ids = new Set<string>();
    for (const job of projectedJobs) {
      if (job.status === "launching" || job.status === "running") {
        ids.add(job.feedbackId);
      }
    }
    return ids;
  }, [projectedJobs]);

  const addJob = useCallback((job: PrismOptimizationJob) => {
    setJobs((prev) => [job, ...prev].slice(0, 8));
    setActiveJobId(job.id);
  }, []);

  const updateJob = useCallback((
    jobId: string,
    updater: (job: PrismOptimizationJob) => PrismOptimizationJob,
  ) => {
    setJobs((prev) =>
      prev.map((job) => (job.id === jobId ? updater(job) : job)),
    );
  }, []);

  useEffect(() => {
    if (!workspaceId || executionIds.length === 0) {
      return;
    }
    const expectedIds = new Set(executionIds);
    let cancelled = false;
    const hydrate = () => {
      void listExecutions({ workspace_id: workspaceId, limit: 20 })
        .then(({ items }) => {
          if (cancelled) {
            return;
          }
          for (const item of items) {
            if (
              expectedIds.has(item.id) ||
              item.feature_id === "prism_selection_optimize"
            ) {
              upsertExecution(item);
            }
          }
        })
        .catch(() => {
          // The chat stream already launched the run; polling is best-effort for the small Prism trace.
        });
    };
    hydrate();
    const interval = window.setInterval(hydrate, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [
    executionIdKey,
    executionIds,
    upsertExecution,
    workspaceId,
  ]);

  useEffect(() => {
    for (const record of records) {
      if (
        !TERMINAL_PRISM_EXECUTION_STATUSES.has(record.status) ||
        syncedExecutionsRef.current.has(record.id)
      ) {
        continue;
      }
      syncedExecutionsRef.current.add(record.id);
      if (jobStatusFromExecution(record) === "completed") {
        void loadProject(projectId)
          .then(() => {
            onReviewStateChanged?.();
            onFeedbackStatus("研究团队已生成待复核修改，请在 Prism 待复核写入中预览并应用。");
          })
          .catch(() => {
            onFeedbackStatus("研究团队已完成优化，请刷新后查看 Prism 待复核写入。");
          });
      }
    }
  }, [
    loadProject,
    onFeedbackStatus,
    onReviewStateChanged,
    records,
    projectId,
  ]);

  return {
    jobs: projectedJobs,
    activeJob,
    activeRecord,
    activePhases,
    optimizingFeedbackIds,
    activeJobId,
    isTraceOpen,
    setActiveJobId,
    setTraceOpen,
    addJob,
    updateJob,
  };
}
