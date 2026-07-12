import { describe, expect, it } from "vitest";

import type { MissionView } from "@/lib/api/mission-types";
import {
  defaultMissionSurface,
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
    reviewItems: [
      { id: "r-low", title: "研究摘要", targetKind: "document", riskLevel: "low", status: "pending", suggestedSelected: true, batchAcceptable: true },
      { id: "r-claim", title: "核心论断", targetKind: "claim", riskLevel: "high", status: "pending", suggestedSelected: false, batchAcceptable: false },
    ],
    reviewSummary: { pending: 2, needsMoreEvidence: 0, accepted: 0, committed: 0 },
    reviewMode: "balanced_default",
    reviewPolicy: { protectedOutputsRequireConfirmation: true, draftOutputsMayBeAutomatic: true },
    reviewSelectionRevision: 3,
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

});
