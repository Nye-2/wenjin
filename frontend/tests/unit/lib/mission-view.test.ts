import { describe, expect, it } from "vitest";

import type { MissionView } from "@/lib/api/mission-types";
import {
  defaultMissionSurface,
  mergeMissionView,
  missionDemandKey,
  missionNeedsAttention,
  suggestedReviewSelection,
} from "@/lib/mission-view";

function view(): MissionView {
  return {
    missionId: "mission-1",
    workspaceId: "ws-1",
    title: "梳理联邦微调研究空白",
    executionStatus: "completed",
    statusLabel: "研究已完成",
    activity: { state: "completed", title: "研究任务已完成" },
    currentOperation: null,
    inputSummary: { total: 0, ready: 0, failed: 0, names: [] },
    failure: null,
    attentionRequest: null,
    createdAt: "2026-07-11T00:00:00Z",
    updatedAt: "2026-07-11T00:10:00Z",
    stages: [],
    requiredStageIds: [],
    subagents: [],
    evidenceItems: [],
    artifactItems: [],
    evidenceCount: 0,
    artifactCount: 0,
    artifactRevision: "artifact-revision-1",
    reviewItems: [
      { id: "r-low", title: "研究摘要", targetKind: "document", riskLevel: "low", status: "pending", suggestedSelected: true, batchAcceptable: true, requiresExplicitReview: false, previewAvailable: false, commitEligible: false },
      { id: "r-claim", title: "核心论断", targetKind: "claim", riskLevel: "high", status: "pending", suggestedSelected: false, batchAcceptable: false, requiresExplicitReview: true, previewAvailable: false, commitEligible: false },
    ],
    reviewSummary: { pending: 2, needsMoreEvidence: 0, accepted: 0, committed: 0 },
    reviewMode: "balanced_default",
    reviewPolicy: { protectedOutputsRequireConfirmation: true, draftOutputsMayBeAutomatic: true },
    reviewSelectionRevision: "review-selection-revision-3",
    commitSummary: { pending: 0, applying: 0, committed: 0, failed: 0 },
    qualityHighlights: [],
    lastItemSeq: 18,
    stateVersion: 7,
  };
}

describe("MissionView projection", () => {
  it("keeps execution completion independent from pending review", () => {
    const mission = view();
    expect(mission.executionStatus).toBe("completed");
    expect(missionNeedsAttention(mission)).toBe(true);
    expect(defaultMissionSurface(mission)).toBe("review");
    expect(missionDemandKey(mission)).toContain("completed");
  });

  it("uses server suggestions without selecting protected review items", () => {
    expect(suggestedReviewSelection(view())).toEqual(["r-low"]);
  });

  it("keeps active generation on progress even when an output is already confirmable", () => {
    const mission = view();
    mission.executionStatus = "running";

    expect(defaultMissionSurface(mission)).toBe("progress");
  });

  it("merges one MissionView monotonically by stateVersion", () => {
    const current = view();
    const older = { ...current, stateVersion: 6, title: "stale title" };
    const newer = { ...current, stateVersion: 8, title: "new title" };

    expect(mergeMissionView(current, older)).toBe(current);
    expect(mergeMissionView(current, newer)).toBe(newer);

    const otherMission = { ...older, missionId: "mission-2" };
    expect(mergeMissionView(current, otherMission)).toBe(otherMission);
  });

  it("keys demand by canonical review and attention identity, not stateVersion", () => {
    const mission = view();
    const key = missionDemandKey(mission);

    expect(missionDemandKey({ ...mission, stateVersion: 8 })).toBe(key);
    expect(missionDemandKey({
      ...mission,
      reviewSelectionRevision: "review-selection-revision-4",
      stateVersion: 8,
    })).not.toBe(key);
    expect(missionDemandKey({
      ...mission,
      attentionRequest: {
        requestId: "attention-1",
        reason: "missing_input",
        title: "需要补充信息",
        summary: "请确认研究范围",
        impact: "确认后继续",
        requiredInputs: [],
        actions: [],
      },
    })).not.toBe(key);
  });

});
