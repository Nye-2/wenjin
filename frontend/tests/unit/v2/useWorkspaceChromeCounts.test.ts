import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getWorkspaceMissionSummaryMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/missions", () => ({
  getWorkspaceMissionSummary: (...args: unknown[]) =>
    getWorkspaceMissionSummaryMock(...args),
}));

import {
  useWorkspaceChromeCounts,
  workspaceChromeCountsFromSummary,
} from "@/app/(workbench)/workspaces/[id]/components/shell/useWorkspaceChromeCounts";
import type {
  MissionSummary,
  MissionWorkspaceSummary,
} from "@/lib/api/mission-types";

function missionSummary(
  missionId: string,
  executionStatus: MissionSummary["executionStatus"],
): MissionSummary {
  return {
    missionId,
    title: missionId,
    executionStatus,
    statusLabel: executionStatus,
    updatedAt: "2026-07-12T00:00:01Z",
    pendingReviewCount: 99,
    evidenceCount: 99,
    artifactCount: 99,
  };
}

describe("workspaceChromeCountsFromSummary", () => {
  beforeEach(() => {
    getWorkspaceMissionSummaryMock.mockReset();
  });

  it("uses only canonical server summary counts and active status", () => {
    const summary: MissionWorkspaceSummary = {
      total: 8,
      statusCounts: { completed: 3, running: 1 },
      pendingReviewCount: 2,
      evidenceCount: 5,
      artifactCount: 4,
      latest: missionSummary("latest", "completed"),
      active: missionSummary("active", "waiting"),
      eventCursor: "cursor-1",
    };

    expect(workspaceChromeCountsFromSummary(summary)).toEqual({
      pendingReviewCount: 2,
      missionStatus: "waiting",
      completedRunCount: 3,
      summaryState: "ready",
    });
  });

  it("does not infer an active Mission from latest or total counts", () => {
    const summary: MissionWorkspaceSummary = {
      total: 12,
      statusCounts: { completed: 7, running: 4 },
      pendingReviewCount: 0,
      evidenceCount: 0,
      artifactCount: 0,
      latest: missionSummary("latest", "running"),
      active: null,
      eventCursor: "cursor-2",
    };

    expect(workspaceChromeCountsFromSummary(summary)).toEqual({
      pendingReviewCount: 0,
      missionStatus: null,
      completedRunCount: 7,
      summaryState: "ready",
    });
  });

  it("exposes an unavailable state instead of treating a failed initial read as zero", async () => {
    getWorkspaceMissionSummaryMock.mockRejectedValueOnce(new Error("offline"));

    const { result } = renderHook(() => useWorkspaceChromeCounts("ws-1"));

    await waitFor(() => expect(result.current.summaryState).toBe("unavailable"));
    expect(result.current.pendingReviewCount).toBe(0);
  });

  it("keeps the last trusted counts and marks them stale after a refresh failure", async () => {
    const summary: MissionWorkspaceSummary = {
      total: 3,
      statusCounts: { completed: 2, running: 1 },
      pendingReviewCount: 4,
      evidenceCount: 5,
      artifactCount: 2,
      latest: missionSummary("active", "running"),
      active: missionSummary("active", "running"),
      eventCursor: "cursor-3",
    };
    getWorkspaceMissionSummaryMock
      .mockResolvedValueOnce(summary)
      .mockRejectedValueOnce(new Error("offline"));

    const { result, rerender } = renderHook(
      ({ refreshKey }) => useWorkspaceChromeCounts("ws-1", refreshKey),
      { initialProps: { refreshKey: 0 } },
    );
    await waitFor(() => expect(result.current.summaryState).toBe("ready"));

    rerender({ refreshKey: 1 });

    await waitFor(() => expect(result.current.summaryState).toBe("stale"));
    expect(result.current).toMatchObject({
      pendingReviewCount: 4,
      missionStatus: "running",
      completedRunCount: 2,
    });
  });
});
