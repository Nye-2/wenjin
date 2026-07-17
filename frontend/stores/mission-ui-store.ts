import { create } from "zustand";

import type { MissionConsoleSurface } from "@/lib/mission-view";

export type MissionPanelMode = "closed" | "peek" | "expanded";

interface MissionUiState {
  focusedMissionId: string | null;
  continuationMissionId: string | null;
  highlightedMissionId: string | null;
  panelMode: MissionPanelMode;
  surface: MissionConsoleSurface;
  evidenceQuery: string;
  selectedReviewItemIds: Set<string>;
  selectionMissionId: string | null;
  selectionRevision: string | null;
  submittingReviewMissionIds: Set<string>;
  focusMission(missionId: string, surface?: MissionConsoleSurface): void;
  peekMission(missionId: string): void;
  expandMission(surface?: MissionConsoleSurface): void;
  closePanel(): void;
  setSurface(surface: MissionConsoleSurface): void;
  setEvidenceQuery(query: string): void;
  setContinuationMission(missionId: string | null): void;
  consumeContinuationMission(missionId: string): void;
  ensureReviewSelection(missionId: string, revision: string, ids: string[]): void;
  setReviewSelection(missionId: string, revision: string, ids: string[]): void;
  toggleReviewItem(missionId: string, revision: string, id: string): void;
  beginReviewSubmission(missionId: string): boolean;
  endReviewSubmission(missionId: string): void;
  clearWorkspaceFocus(): void;
}

export const useMissionUiStore = create<MissionUiState>((set, get) => ({
  focusedMissionId: null,
  continuationMissionId: null,
  highlightedMissionId: null,
  panelMode: "closed",
  surface: "progress",
  evidenceQuery: "",
  selectedReviewItemIds: new Set<string>(),
  selectionMissionId: null,
  selectionRevision: null,
  submittingReviewMissionIds: new Set<string>(),
  focusMission: (missionId, surface) =>
    set((state) => ({
      focusedMissionId: missionId,
      highlightedMissionId: missionId,
      panelMode: "expanded",
      surface: surface ?? state.surface,
    })),
  peekMission: (missionId) =>
    set((state) => ({
      focusedMissionId: missionId,
      highlightedMissionId: missionId,
      panelMode: state.panelMode === "expanded" ? "expanded" : "peek",
    })),
  expandMission: (surface) =>
    set((state) => ({
      panelMode: "expanded",
      surface: surface ?? state.surface,
    })),
  closePanel: () =>
    set({
      focusedMissionId: null,
      panelMode: "closed",
    }),
  setSurface: (surface) => set({ surface, panelMode: "expanded" }),
  setEvidenceQuery: (evidenceQuery) => set({ evidenceQuery }),
  setContinuationMission: (continuationMissionId) => set({ continuationMissionId }),
  consumeContinuationMission: (missionId) =>
    set((state) => state.continuationMissionId === missionId
      ? { continuationMissionId: null }
      : state),
  ensureReviewSelection: (selectionMissionId, selectionRevision, ids) =>
    set((state) => {
      if (
        state.selectionMissionId === selectionMissionId &&
        state.selectionRevision === selectionRevision
      ) {
        return state;
      }
      return {
        selectionMissionId,
        selectionRevision,
        selectedReviewItemIds: new Set(ids),
      };
    }),
  setReviewSelection: (selectionMissionId, selectionRevision, ids) =>
    set({
      selectionMissionId,
      selectionRevision,
      selectedReviewItemIds: new Set(ids),
    }),
  toggleReviewItem: (selectionMissionId, selectionRevision, id) =>
    set((state) => {
      const selectedReviewItemIds =
        state.selectionMissionId === selectionMissionId &&
        state.selectionRevision === selectionRevision
          ? new Set(state.selectedReviewItemIds)
          : new Set<string>();
      if (selectedReviewItemIds.has(id)) selectedReviewItemIds.delete(id);
      else selectedReviewItemIds.add(id);
      return { selectionMissionId, selectionRevision, selectedReviewItemIds };
    }),
  beginReviewSubmission: (missionId) => {
    const current = get().submittingReviewMissionIds;
    if (current.has(missionId)) return false;
    set({ submittingReviewMissionIds: new Set(current).add(missionId) });
    return true;
  },
  endReviewSubmission: (missionId) =>
    set((state) => {
      if (!state.submittingReviewMissionIds.has(missionId)) return state;
      const submittingReviewMissionIds = new Set(state.submittingReviewMissionIds);
      submittingReviewMissionIds.delete(missionId);
      return { submittingReviewMissionIds };
    }),
  clearWorkspaceFocus: () =>
    set({
      focusedMissionId: null,
      continuationMissionId: null,
      highlightedMissionId: null,
      panelMode: "closed",
      evidenceQuery: "",
      selectedReviewItemIds: new Set<string>(),
      selectionMissionId: null,
      selectionRevision: null,
      submittingReviewMissionIds: new Set<string>(),
    }),
}));
