"use client";

import { useEffect, useState } from "react";
import { listWorkspaceMissions } from "@/lib/api/missions";

export function useWorkspaceChromeCounts(workspaceId: string, pendingReviewFallback = 0) {
  const [counts, setCounts] = useState({ pendingReviewCount: pendingReviewFallback, missionStatus: null as "running" | "waiting" | null, completedRunCount: 0 });
  useEffect(() => {
    let cancelled = false;
    listWorkspaceMissions(workspaceId).then((items) => {
      if (cancelled) return;
      setCounts({
        pendingReviewCount: Math.max(pendingReviewFallback, items.reduce((sum, item) => sum + item.pendingReviewCount, 0)),
        missionStatus: items.some((item) => item.executionStatus === "waiting")
          ? "waiting"
          : items.some((item) => ["created", "planning", "running"].includes(item.executionStatus))
            ? "running"
            : null,
        completedRunCount: items.filter((item) => item.executionStatus === "completed").length,
      });
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [pendingReviewFallback, workspaceId]);
  return counts;
}
