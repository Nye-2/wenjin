import { beforeEach, describe, expect, it } from "vitest";
import { useMissionUiStore } from "@/stores/mission-ui-store";

describe("mission-ui-store", () => {
  beforeEach(() => useMissionUiStore.getState().clearWorkspaceFocus());

  it("stores focus and panel preferences without lifecycle truth", () => {
    useMissionUiStore.getState().peekMission("mission-1");
    expect(useMissionUiStore.getState()).toMatchObject({ activeMissionId: "mission-1", panelMode: "peek" });
    expect("executionStatus" in useMissionUiStore.getState()).toBe(false);
    useMissionUiStore.getState().focusMission("mission-1", "review");
    expect(useMissionUiStore.getState()).toMatchObject({ focusedMissionId: "mission-1", panelMode: "expanded", surface: "review" });
  });

  it("tracks a review selection only for its server revision", () => {
    useMissionUiStore.getState().setReviewSelection(["review-1"], 4);
    expect(useMissionUiStore.getState().selectedReviewItemIds.has("review-1")).toBe(true);
    expect(useMissionUiStore.getState().selectionRevision).toBe(4);
  });

  it("detaches Mission focus when the console closes", () => {
    useMissionUiStore.getState().focusMission("mission-1", "review");
    useMissionUiStore.getState().setReviewSelection(["review-1"], 4);

    useMissionUiStore.getState().closePanel();

    expect(useMissionUiStore.getState()).toMatchObject({
      focusedMissionId: null,
      panelMode: "closed",
      selectionRevision: null,
    });
    expect(useMissionUiStore.getState().selectedReviewItemIds.size).toBe(0);
  });
});
