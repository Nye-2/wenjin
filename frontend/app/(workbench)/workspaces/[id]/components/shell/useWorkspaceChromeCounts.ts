"use client";

import { useExecutionStore } from "@/stores/execution-store";
import { useRunUiStore } from "@/stores/run-ui-store";
import { extractTaskReport } from "@/lib/workbench-result-outputs";

const ACTIVE_EXECUTION_STATUSES = new Set(["pending", "running", "paused"]);

export function useWorkspaceChromeCounts(
  workspaceId: string,
  pendingReviewFallback = 0,
) {
  const executionPendingReviewCount = useExecutionStore((state) => {
    let pendingReviewCount = 0;

    for (const record of state.executions.values()) {
      if (record.workspace_id && record.workspace_id !== workspaceId) {
        continue;
      }
      pendingReviewCount += record.review_items?.length ?? 0;
      const taskReport = extractTaskReport(record.result);
      const reviewPacket = taskReport?.review_packet;
      if (
        reviewPacket &&
        typeof reviewPacket === "object" &&
        !Array.isArray(reviewPacket)
      ) {
        const items = (reviewPacket as Record<string, unknown>).items;
        pendingReviewCount += Array.isArray(items) ? items.length : 0;
      }
    }

    return pendingReviewCount;
  });
  const activeRunCount = useExecutionStore((state) => {
    let count = 0;

    for (const record of state.executions.values()) {
      if (record.workspace_id && record.workspace_id !== workspaceId) {
        continue;
      }
      if (ACTIVE_EXECUTION_STATUSES.has(record.status)) {
        count += 1;
      }
    }

    return count;
  });
  const completedRunCount = useRunUiStore(
    (state) => state.completedRunIds.size,
  );

  return {
    pendingReviewCount: Math.max(
      executionPendingReviewCount,
      pendingReviewFallback,
    ),
    activeRunCount,
    completedRunCount,
  };
}
