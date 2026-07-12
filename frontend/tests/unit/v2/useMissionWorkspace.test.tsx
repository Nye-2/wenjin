import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MissionEventHint, MissionView } from "@/lib/api/mission-types";

const { getMissionViewMock, listWorkspaceMissionsMock, subscribeMissionEventsMock } = vi.hoisted(() => ({
  getMissionViewMock: vi.fn(),
  listWorkspaceMissionsMock: vi.fn(),
  subscribeMissionEventsMock: vi.fn(),
}));

vi.mock("@/lib/api/missions", () => ({
  getMissionView: getMissionViewMock,
  listWorkspaceMissions: listWorkspaceMissionsMock,
  subscribeMissionEvents: subscribeMissionEventsMock,
}));

import { useMissionWorkspace } from "@/app/(workbench)/workspaces/[id]/components/mission-console/useMissionWorkspace";

function missionView(missionId: string): MissionView {
  return {
    missionId,
    workspaceId: "workspace-1",
    title: missionId,
    executionStatus: "running",
    statusLabel: "正在研究",
    attentionRequest: null,
    createdAt: "2026-07-12T00:00:00Z",
    updatedAt: "2026-07-12T00:00:01Z",
    stages: [],
    requiredStageIds: [],
    subagents: [],
    evidenceItems: [],
    artifactItems: [],
    evidenceCount: 0,
    artifactCount: 0,
    reviewItems: [],
    reviewSummary: { pending: 0, needsMoreEvidence: 0, accepted: 0, committed: 0 },
    reviewMode: "balanced_default",
    reviewPolicy: { protectedOutputsRequireConfirmation: true, draftOutputsMayBeAutomatic: true },
    reviewSelectionRevision: 1,
    commitSummary: { pending: 0, applying: 0, committed: 0, failed: 0 },
    qualityHighlights: [],
    lastItemSeq: 1,
    stateVersion: 1,
  };
}

describe("useMissionWorkspace focus isolation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listWorkspaceMissionsMock.mockResolvedValue([{ missionId: "mission-a" }]);
    getMissionViewMock.mockImplementation(async (missionId: string) => missionView(missionId));
  });

  it("does not replace the focused MissionView when another Mission emits an event", async () => {
    let onEvent: ((event: MissionEventHint) => void) | undefined;
    subscribeMissionEventsMock.mockImplementation((options: { onEvent(event: MissionEventHint): void }) => {
      onEvent = options.onEvent;
      return () => undefined;
    });

    const { result } = renderHook(() => useMissionWorkspace("workspace-1", "mission-a"));
    await waitFor(() => expect(result.current.view?.missionId).toBe("mission-a"));
    expect(getMissionViewMock).toHaveBeenCalledTimes(1);

    act(() => {
      onEvent?.({
        type: "mission.updated",
        missionId: "mission-b",
        stateVersion: 2,
        lastItemSeq: 2,
        replayRequired: false,
        cursor: "cursor-b",
      });
    });
    await new Promise((resolve) => setTimeout(resolve, 120));
    expect(getMissionViewMock).toHaveBeenCalledTimes(1);
    expect(result.current.view?.missionId).toBe("mission-a");

    act(() => {
      onEvent?.({
        type: "mission.updated",
        missionId: "mission-a",
        stateVersion: 2,
        lastItemSeq: 2,
        replayRequired: false,
        cursor: "cursor-a",
      });
    });
    await waitFor(() => expect(getMissionViewMock).toHaveBeenCalledTimes(2));
    expect(getMissionViewMock).toHaveBeenLastCalledWith("mission-a");
  });
});
