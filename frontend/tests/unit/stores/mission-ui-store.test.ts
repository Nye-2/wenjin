import { beforeEach, describe, expect, it } from "vitest";
import { useMissionUiStore } from "@/stores/mission-ui-store";

describe("mission-ui-store", () => {
  beforeEach(() => useMissionUiStore.getState().clearWorkspaceFocus());

  it("stores focus and panel preferences without lifecycle truth", () => {
    useMissionUiStore.getState().peekMission("mission-1");
    expect(useMissionUiStore.getState()).toMatchObject({ focusedMissionId: "mission-1", panelMode: "peek" });
    expect("executionStatus" in useMissionUiStore.getState()).toBe(false);
    useMissionUiStore.getState().focusMission("mission-1", "review");
    expect(useMissionUiStore.getState()).toMatchObject({ focusedMissionId: "mission-1", panelMode: "expanded", surface: "review" });
  });

  it("keeps display focus separate from the one-shot chat continuation target", () => {
    useMissionUiStore.getState().focusMission("mission-history", "artifacts");
    expect(useMissionUiStore.getState().continuationMissionId).toBeNull();

    useMissionUiStore.getState().setContinuationMission("mission-active");
    useMissionUiStore.getState().focusMission("mission-history-2", "progress");
    expect(useMissionUiStore.getState()).toMatchObject({
      focusedMissionId: "mission-history-2",
      continuationMissionId: "mission-active",
    });

    useMissionUiStore.getState().consumeContinuationMission("mission-history-2");
    expect(useMissionUiStore.getState().continuationMissionId).toBe("mission-active");
    useMissionUiStore.getState().consumeContinuationMission("mission-active");
    expect(useMissionUiStore.getState().continuationMissionId).toBeNull();
  });

  it("follows a newly launched Mission even while an older Mission is expanded", () => {
    useMissionUiStore.getState().focusMission("mission-old", "artifacts");

    useMissionUiStore.getState().peekMission("mission-new");

    expect(useMissionUiStore.getState()).toMatchObject({
      focusedMissionId: "mission-new",
      highlightedMissionId: "mission-new",
      panelMode: "expanded",
      surface: "artifacts",
    });
  });

  it("tracks a review selection only for its server revision", () => {
    useMissionUiStore.getState().setReviewSelection(
      "mission-1",
      "revision-4",
      ["review-1"],
    );
    expect(useMissionUiStore.getState().selectedReviewItemIds.has("review-1")).toBe(true);
    expect(useMissionUiStore.getState()).toMatchObject({
      selectionMissionId: "mission-1",
      selectionRevision: "revision-4",
    });
  });

  it("keeps a review selection when the console closes", () => {
    useMissionUiStore.getState().focusMission("mission-1", "review");
    useMissionUiStore.getState().setReviewSelection(
      "mission-1",
      "revision-4",
      ["review-1"],
    );

    useMissionUiStore.getState().closePanel();

    expect(useMissionUiStore.getState()).toMatchObject({
      focusedMissionId: null,
      panelMode: "closed",
      selectionMissionId: "mission-1",
      selectionRevision: "revision-4",
    });
    expect(useMissionUiStore.getState().selectedReviewItemIds.has("review-1")).toBe(true);
  });

  it("initializes suggestions once per Mission and server revision", () => {
    const store = useMissionUiStore.getState();
    store.ensureReviewSelection("mission-1", "revision-1", ["review-1"]);
    store.toggleReviewItem("mission-1", "revision-1", "review-1");

    useMissionUiStore.getState().ensureReviewSelection(
      "mission-1",
      "revision-1",
      ["review-1"],
    );
    expect(useMissionUiStore.getState().selectedReviewItemIds.size).toBe(0);

    useMissionUiStore.getState().ensureReviewSelection(
      "mission-1",
      "revision-2",
      ["review-2"],
    );
    expect(useMissionUiStore.getState().selectedReviewItemIds).toEqual(new Set(["review-2"]));

    useMissionUiStore.getState().ensureReviewSelection(
      "mission-2",
      "revision-2",
      ["review-3"],
    );
    expect(useMissionUiStore.getState()).toMatchObject({
      selectionMissionId: "mission-2",
      selectionRevision: "revision-2",
    });
    expect(useMissionUiStore.getState().selectedReviewItemIds).toEqual(new Set(["review-3"]));
  });

  it("acquires one synchronous review submission lock per Mission", () => {
    expect(useMissionUiStore.getState().beginReviewSubmission("mission-1")).toBe(true);
    expect(useMissionUiStore.getState().beginReviewSubmission("mission-1")).toBe(false);
    expect(useMissionUiStore.getState().beginReviewSubmission("mission-2")).toBe(true);

    useMissionUiStore.getState().endReviewSubmission("mission-1");
    expect(useMissionUiStore.getState().beginReviewSubmission("mission-1")).toBe(true);
  });
});
