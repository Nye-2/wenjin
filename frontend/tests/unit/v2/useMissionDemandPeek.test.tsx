import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useMissionDemandPeek } from "@/app/(workbench)/workspaces/[id]/components/mission-console/useMissionDemandPeek";
import type { MissionView } from "@/lib/api/mission-types";
import { useMissionUiStore } from "@/stores/mission-ui-store";

function missionView(overrides: Partial<MissionView> = {}): MissionView {
  return {
    missionId: "mission-1",
    workspaceId: "workspace-1",
    title: "研究任务",
    executionStatus: "running",
    statusLabel: "正在研究",
    activity: { state: "working", title: "正在研究" },
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
    reviewSummary: {
      pending: 0,
      needsMoreEvidence: 0,
      accepted: 0,
      committed: 0,
    },
    reviewMode: "balanced_default",
    reviewPolicy: {
      protectedOutputsRequireConfirmation: true,
      draftOutputsMayBeAutomatic: true,
    },
    reviewSelectionRevision: "review-revision-1",
    commitSummary: { pending: 0, applying: 0, committed: 0, failed: 0 },
    qualityHighlights: [],
    lastItemSeq: 1,
    stateVersion: 1,
    ...overrides,
    currentOperation: overrides.currentOperation ?? null,
    inputSummary: overrides.inputSummary ?? { total: 0, ready: 0, failed: 0, names: [] },
    failure: overrides.failure ?? null,
  };
}

describe("useMissionDemandPeek", () => {
  beforeEach(() => useMissionUiStore.getState().clearWorkspaceFocus());

  it("peeks only when a closed panel receives a new review or attention demand", () => {
    const initialView = missionView();
    const { result, rerender } = renderHook(
      ({ view }) => useMissionDemandPeek({
        workspaceId: "workspace-1",
        view,
        loading: false,
      }),
      { initialProps: { view: initialView } },
    );

    expect(useMissionUiStore.getState().panelMode).toBe("closed");

    rerender({ view: { ...initialView, stateVersion: 2 } });
    expect(useMissionUiStore.getState().panelMode).toBe("closed");

    const reviewView = missionView({
      stateVersion: 3,
      reviewSelectionRevision: "review-revision-2",
      reviewSummary: {
        pending: 1,
        needsMoreEvidence: 0,
        accepted: 0,
        committed: 0,
      },
    });
    rerender({ view: reviewView });
    expect(useMissionUiStore.getState()).toMatchObject({
      panelMode: "peek",
      focusedMissionId: "mission-1",
    });

    act(() => {
      result.current.acknowledgeCurrentDemand();
      useMissionUiStore.getState().closePanel();
    });
    rerender({ view: { ...reviewView, stateVersion: 4 } });
    expect(useMissionUiStore.getState().panelMode).toBe("closed");

    rerender({
      view: missionView({
        stateVersion: 5,
        attentionRequest: {
          requestId: "attention-1",
          reason: "missing_input",
          title: "需要补充信息",
          summary: "请确认研究范围",
          impact: "确认后继续",
          requiredInputs: [],
          actions: [],
        },
      }),
    });
    expect(useMissionUiStore.getState()).toMatchObject({
      panelMode: "peek",
      focusedMissionId: "mission-1",
    });
  });
});
