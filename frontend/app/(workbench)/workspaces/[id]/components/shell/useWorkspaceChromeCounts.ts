"use client";

import { useEffect, useState } from "react";
import { getWorkspaceMissionSummary } from "@/lib/api/missions";
import type { MissionWorkspaceSummary } from "@/lib/api/mission-types";

export type WorkspaceChromeCounts = {
  pendingReviewCount: number;
  missionStatus: "running" | "waiting" | null;
  completedRunCount: number;
  summaryState: "loading" | "ready" | "stale" | "unavailable";
};

const EMPTY_COUNTS: WorkspaceChromeCounts = {
  pendingReviewCount: 0,
  missionStatus: null,
  completedRunCount: 0,
  summaryState: "loading",
};

export function workspaceChromeCountsFromSummary(
  summary: MissionWorkspaceSummary,
): WorkspaceChromeCounts {
  const activeStatus = summary.active?.executionStatus ?? null;
  return {
    pendingReviewCount: summary.pendingReviewCount,
    missionStatus: activeStatus === "waiting"
      ? "waiting"
      : activeStatus && ["created", "planning", "running"].includes(activeStatus)
        ? "running"
        : null,
    completedRunCount: summary.statusCounts.completed ?? 0,
    summaryState: "ready",
  };
}

export function useWorkspaceChromeCounts(
  workspaceId: string,
  refreshKey?: string | number | null,
) {
  const [counts, setCounts] = useState<WorkspaceChromeCounts>(EMPTY_COUNTS);
  useEffect(() => setCounts(EMPTY_COUNTS), [workspaceId]);
  useEffect(() => {
    let cancelled = false;
    getWorkspaceMissionSummary(workspaceId).then((summary) => {
      if (cancelled) return;
      setCounts(workspaceChromeCountsFromSummary(summary));
    }).catch(() => {
      if (cancelled) return;
      setCounts((current) => current.summaryState === "ready" || current.summaryState === "stale"
        ? { ...current, summaryState: "stale" }
        : { ...EMPTY_COUNTS, summaryState: "unavailable" });
    });
    return () => { cancelled = true; };
  }, [refreshKey, workspaceId]);
  return counts;
}
