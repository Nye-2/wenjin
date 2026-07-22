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

function missionView(missionId: string, stateVersion = 1): MissionView {
  return {
    missionId,
    workspaceId: "workspace-1",
    title: missionId,
    executionStatus: "running",
    statusLabel: "正在研究",
    activity: { state: "working", title: "问津正在推进当前研究" },
    currentOperation: null,
    inputSummary: { total: 0, ready: 0, failed: 0, names: [] },
    failure: null,
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
    artifactRevision: "artifact-revision-1",
    reviewItems: [],
    reviewSummary: { pending: 0, needsMoreEvidence: 0, accepted: 0, committed: 0 },
    reviewMode: "balanced_default",
    reviewPolicy: { protectedOutputsRequireConfirmation: true, draftOutputsMayBeAutomatic: true },
    reviewSelectionRevision: "review-selection-revision-1",
    commitSummary: { pending: 0, applying: 0, committed: 0, failed: 0 },
    qualityHighlights: [],
    lastItemSeq: 1,
    stateVersion,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe("useMissionWorkspace identity isolation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listWorkspaceMissionsMock.mockResolvedValue([{ missionId: "mission-a" }]);
    getMissionViewMock.mockImplementation(async (missionId: string) => missionView(missionId));
    subscribeMissionEventsMock.mockReturnValue(() => undefined);
  });

  it("never changes Mission identity because an unrelated SSE event arrived", async () => {
    let onEvent: ((event: MissionEventHint) => void) | undefined;
    subscribeMissionEventsMock.mockImplementation((options: { onEvent(event: MissionEventHint): void }) => {
      onEvent = options.onEvent;
      return () => undefined;
    });

    const { result } = renderHook(() => useMissionWorkspace("workspace-1"));
    await waitFor(() => expect(result.current.view?.missionId).toBe("mission-a"));
    expect(getMissionViewMock).toHaveBeenCalledTimes(1);

    act(() => {
      onEvent?.({
        type: "mission.updated",
        missionId: "mission-b",
        stateVersion: 2,
        lastItemSeq: 2,
        cursor: "cursor-b",
      });
    });
    await new Promise((resolve) => setTimeout(resolve, 120));

    expect(getMissionViewMock).toHaveBeenCalledTimes(1);
    expect(result.current.view?.missionId).toBe("mission-a");
  });

  it("adopts the first Mission announced by SSE when the workspace is empty", async () => {
    let onEvent: ((event: MissionEventHint) => void) | undefined;
    listWorkspaceMissionsMock.mockResolvedValueOnce([]);
    subscribeMissionEventsMock.mockImplementation((options: { onEvent(event: MissionEventHint): void }) => {
      onEvent = options.onEvent;
      return () => undefined;
    });
    const { result } = renderHook(() => useMissionWorkspace("workspace-1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    act(() => {
      onEvent?.({
        type: "mission.updated",
        missionId: "mission-new",
        stateVersion: 1,
        lastItemSeq: 1,
        cursor: "cursor-new",
      });
    });

    await waitFor(() => expect(result.current.view?.missionId).toBe("mission-new"));
    expect(getMissionViewMock).toHaveBeenCalledWith("mission-new");
  });

  it("refreshes only the visible Mission after its SSE version advances", async () => {
    let onEvent: ((event: MissionEventHint) => void) | undefined;
    subscribeMissionEventsMock.mockImplementation((options: { onEvent(event: MissionEventHint): void }) => {
      onEvent = options.onEvent;
      return () => undefined;
    });
    getMissionViewMock.mockImplementation(async (missionId: string) =>
      missionView(missionId, getMissionViewMock.mock.calls.length),
    );
    const { result } = renderHook(() => useMissionWorkspace("workspace-1"));
    await waitFor(() => expect(result.current.view?.missionId).toBe("mission-a"));

    act(() => {
      onEvent?.({
        type: "mission.updated",
        missionId: "mission-a",
        stateVersion: 2,
        lastItemSeq: 2,
        cursor: "cursor-a",
      });
    });

    await waitFor(() => expect(getMissionViewMock).toHaveBeenCalledTimes(2));
    expect(getMissionViewMock).toHaveBeenLastCalledWith("mission-a");
    expect(result.current.view?.missionId).toBe("mission-a");
  });

  it("keeps the last MissionView visible and marks it stale when refresh fails", async () => {
    const { result } = renderHook(() => useMissionWorkspace("workspace-1"));
    await waitFor(() => expect(result.current.view?.missionId).toBe("mission-a"));
    getMissionViewMock.mockRejectedValueOnce(new Error("研究任务更新暂时失败"));

    await act(async () => {
      await result.current.refresh("mission-a");
    });

    expect(result.current.error).toBe("研究任务更新暂时失败");
    expect(result.current.view).toMatchObject({
      missionId: "mission-a",
      isStale: true,
      loadError: "研究任务更新暂时失败",
    });

    await act(async () => {
      await result.current.refresh("mission-a");
    });
    expect(result.current.error).toBeNull();
    expect(result.current.view).toMatchObject({ isStale: false, loadError: null });
  });

  it("marks the current view stale when Mission SSE authentication stops", async () => {
    let onError: ((message: string) => void) | undefined;
    subscribeMissionEventsMock.mockImplementation((options: { onError?(message: string): void }) => {
      onError = options.onError;
      return () => undefined;
    });
    const { result } = renderHook(() => useMissionWorkspace("workspace-1"));
    await waitFor(() => expect(result.current.view?.missionId).toBe("mission-a"));

    act(() => onError?.("登录状态已失效，请重新登录后刷新任务。"));

    expect(result.current.error).toContain("登录状态已失效");
    expect(result.current.view?.isStale).toBe(true);
  });

  it("rejects an older GET projection after a newer stateVersion is visible", async () => {
    getMissionViewMock.mockResolvedValueOnce(missionView("mission-a", 5));
    const { result } = renderHook(() => useMissionWorkspace("workspace-1"));
    await waitFor(() => expect(result.current.view?.stateVersion).toBe(5));

    getMissionViewMock.mockResolvedValueOnce(missionView("mission-a", 4));
    await act(async () => {
      await result.current.refresh("mission-a");
    });
    expect(result.current.view?.stateVersion).toBe(5);

    getMissionViewMock.mockResolvedValueOnce(missionView("mission-a", 6));
    await act(async () => {
      await result.current.refresh("mission-a");
    });
    expect(result.current.view?.stateVersion).toBe(6);
  });

  it("switches identity only through the explicit switch primitive", async () => {
    const onAccepted = vi.fn();
    const { result } = renderHook(() => useMissionWorkspace("workspace-1"));
    await waitFor(() => expect(result.current.view?.missionId).toBe("mission-a"));

    await act(async () => {
      await result.current.switchMission("mission-b", { onAccepted });
    });

    expect(result.current.view?.missionId).toBe("mission-b");
    expect(onAccepted).toHaveBeenCalledWith(expect.objectContaining({ missionId: "mission-b" }));
  });

  it("keeps the current identity and content intact when historical loading fails", async () => {
    const { result } = renderHook(() => useMissionWorkspace("workspace-1"));
    await waitFor(() => expect(result.current.view?.missionId).toBe("mission-a"));
    getMissionViewMock.mockRejectedValueOnce(new Error("历史任务暂时不可用"));

    await act(async () => {
      await result.current.switchMission("mission-b");
    });

    expect(result.current.view).toMatchObject({
      missionId: "mission-a",
      isStale: false,
      loadError: null,
    });
    expect(result.current.error).toBe("历史任务暂时不可用");
    expect(result.current.pendingMissionId).toBeNull();
  });

  it("lets the newest explicit switch win when projections resolve out of order", async () => {
    const missionB = deferred<MissionView>();
    const missionC = deferred<MissionView>();
    getMissionViewMock.mockImplementation((missionId: string) => {
      if (missionId === "mission-b") return missionB.promise;
      if (missionId === "mission-c") return missionC.promise;
      return Promise.resolve(missionView(missionId));
    });
    const { result } = renderHook(() => useMissionWorkspace("workspace-1"));
    await waitFor(() => expect(result.current.view?.missionId).toBe("mission-a"));

    let switchB!: Promise<MissionView | null>;
    let switchC!: Promise<MissionView | null>;
    act(() => {
      switchB = result.current.switchMission("mission-b");
      switchC = result.current.switchMission("mission-c");
    });

    await act(async () => {
      missionB.resolve(missionView("mission-b"));
      await switchB;
    });
    expect(result.current.view?.missionId).toBe("mission-a");

    await act(async () => {
      missionC.resolve(missionView("mission-c"));
      await switchC;
    });
    expect(result.current.view?.missionId).toBe("mission-c");
  });

  it("retries only an explicitly retained command target when its SSE arrives", async () => {
    let onEvent: ((event: MissionEventHint) => void) | undefined;
    subscribeMissionEventsMock.mockImplementation((options: { onEvent(event: MissionEventHint): void }) => {
      onEvent = options.onEvent;
      return () => undefined;
    });
    const onAccepted = vi.fn();
    const { result } = renderHook(() => useMissionWorkspace("workspace-1"));
    await waitFor(() => expect(result.current.view?.missionId).toBe("mission-a"));
    getMissionViewMock.mockRejectedValueOnce(new Error("投影尚未可用"));

    await act(async () => {
      await result.current.switchMission("mission-b", {
        retainOnFailure: true,
        onAccepted,
      });
    });
    expect(result.current.view?.missionId).toBe("mission-a");
    expect(result.current.pendingMissionId).toBe("mission-b");

    getMissionViewMock.mockResolvedValueOnce(missionView("mission-b", 2));
    act(() => {
      onEvent?.({
        type: "mission.updated",
        missionId: "mission-b",
        stateVersion: 2,
        lastItemSeq: 2,
        cursor: "cursor-b",
      });
    });

    await waitFor(() => expect(result.current.view?.missionId).toBe("mission-b"));
    expect(onAccepted).toHaveBeenCalledTimes(1);
  });
});
