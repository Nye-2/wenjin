import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getMissionView } from "@/lib/api/missions";
import type { MissionView } from "@/lib/api/mission-types";
import {
  jobStatusFromMission,
  TERMINAL_PRISM_MISSION_STATUSES,
  type PrismOptimizationJob,
} from "./prismOptimizationJobs";

interface Options {
  workspaceId?: string;
  projectId: string;
  loadProject(projectId: string): Promise<void>;
  onReviewStateChanged?: () => void;
  onFeedbackStatus(message: string): void;
}

export function usePrismOptimizationJobs({ projectId, loadProject, onReviewStateChanged, onFeedbackStatus }: Options) {
  const [jobs, setJobs] = useState<PrismOptimizationJob[]>([]);
  const [missions, setMissions] = useState<Map<string, MissionView>>(new Map());
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [isTraceOpen, setTraceOpen] = useState(false);
  const syncedRef = useRef<Set<string>>(new Set());
  const projectedJobs = useMemo(() => jobs.map((job) => {
    const mission = job.missionId ? missions.get(job.missionId) : null;
    const status = jobStatusFromMission(mission);
    return status && status !== job.status ? { ...job, status } : job;
  }), [jobs, missions]);
  const missionIds = useMemo(() => projectedJobs.map((job) => job.missionId).filter((id): id is string => Boolean(id)), [projectedJobs]);
  const missionKey = missionIds.join("|");
  const activeJob = projectedJobs.find((job) => job.id === activeJobId) ?? projectedJobs[0] ?? null;
  const activeMission = activeJob?.missionId ? missions.get(activeJob.missionId) ?? null : null;
  const optimizingFeedbackIds = useMemo(() => new Set(projectedJobs.filter((job) => job.status === "launching" || job.status === "running").map((job) => job.feedbackId)), [projectedJobs]);
  const addJob = useCallback((job: PrismOptimizationJob) => { setJobs((current) => [job, ...current].slice(0, 8)); setActiveJobId(job.id); }, []);
  const updateJob = useCallback((jobId: string, updater: (job: PrismOptimizationJob) => PrismOptimizationJob) => setJobs((current) => current.map((job) => job.id === jobId ? updater(job) : job)), []);

  useEffect(() => {
    const ids = missionKey ? missionKey.split("|") : [];
    if (!ids.length) return;
    let cancelled = false;
    const hydrate = async () => {
      const loaded = await Promise.all(ids.map((id) => getMissionView(id).catch(() => null)));
      if (!cancelled) setMissions(new Map(loaded.filter((item): item is MissionView => Boolean(item)).map((item) => [item.missionId, item])));
    };
    void hydrate();
    const timer = setInterval(() => void hydrate(), 2500);
    return () => { cancelled = true; clearInterval(timer); };
  }, [missionKey]);

  useEffect(() => {
    for (const mission of missions.values()) {
      if (!TERMINAL_PRISM_MISSION_STATUSES.has(mission.executionStatus) || syncedRef.current.has(mission.missionId)) continue;
      syncedRef.current.add(mission.missionId);
      if (jobStatusFromMission(mission) === "completed") {
        void loadProject(projectId).then(() => {
          onReviewStateChanged?.();
          onFeedbackStatus("问津已生成待确认修改，请在写作台中预览后保存。");
        }).catch(() => onFeedbackStatus("修改已生成，请刷新写作台查看。"));
      }
    }
  }, [loadProject, missions, onFeedbackStatus, onReviewStateChanged, projectId]);

  return { jobs: projectedJobs, activeJob, activeMission, optimizingFeedbackIds, activeJobId, isTraceOpen, setActiveJobId, setTraceOpen, addJob, updateJob };
}
