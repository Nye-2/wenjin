"use client";

import { useEffect, useState } from "react";
import { getWorkspaceMissionSummary } from "@/lib/api/missions";

export function useWorkspaceChromeCounts(workspaceId: string, pendingReviewFallback = 0) {
  const [counts, setCounts] = useState({ pendingReviewCount: pendingReviewFallback, missionStatus: null as "running" | "waiting" | null, completedRunCount: 0 });
  useEffect(() => {
    let cancelled = false;
    getWorkspaceMissionSummary(workspaceId).then((summary) => {
      if (cancelled) return;
      const statuses = summary.statusCounts;
      setCounts({
        pendingReviewCount: Math.max(pendingReviewFallback, summary.pendingReviewCount),
        missionStatus: (statuses.waiting ?? 0) > 0
          ? "waiting"
          : ["created", "planning", "running"].some((status) => (statuses[status] ?? 0) > 0)
            ? "running"
            : null,
        completedRunCount: statuses.completed ?? 0,
      });
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [pendingReviewFallback, workspaceId]);
  return counts;
}
