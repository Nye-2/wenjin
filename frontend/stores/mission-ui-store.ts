import { create } from "zustand";

import type { MissionConsoleSurface } from "@/lib/mission-view";

export type MissionPanelMode = "closed" | "peek" | "expanded";

interface MissionUiState {
  focusedMissionId: string | null;
  highlightedMissionId: string | null;
  focusedPreviewItemId: string | null;
  panelMode: MissionPanelMode;
  surface: MissionConsoleSurface;
  badgeCount: number;
  evidenceQuery: string;
  selectedReviewItemIds: Set<string>;
  selectionRevision: number | null;
  focusMission(missionId: string, surface?: MissionConsoleSurface): void;
  peekMission(missionId: string): void;
  expandMission(surface?: MissionConsoleSurface): void;
  closePanel(): void;
  setSurface(surface: MissionConsoleSurface): void;
  setBadgeCount(count: number): void;
  setEvidenceQuery(query: string): void;
  setReviewSelection(ids: string[], revision: number): void;
  toggleReviewItem(id: string): void;
  clearWorkspaceFocus(): void;
}

export const useMissionUiStore = create<MissionUiState>((set) => ({
  focusedMissionId: null,
  highlightedMissionId: null,
  focusedPreviewItemId: null,
  panelMode: "closed",
  surface: "progress",
  badgeCount: 0,
  evidenceQuery: "",
  selectedReviewItemIds: new Set<string>(),
  selectionRevision: null,
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
      focusedPreviewItemId: null,
      panelMode: "closed",
      selectedReviewItemIds: new Set<string>(),
      selectionRevision: null,
    }),
  setSurface: (surface) => set({ surface, panelMode: "expanded" }),
  setBadgeCount: (badgeCount) => set({ badgeCount: Math.max(0, badgeCount) }),
  setEvidenceQuery: (evidenceQuery) => set({ evidenceQuery }),
  setReviewSelection: (ids, selectionRevision) =>
    set({ selectedReviewItemIds: new Set(ids), selectionRevision }),
  toggleReviewItem: (id) =>
    set((state) => {
      const selectedReviewItemIds = new Set(state.selectedReviewItemIds);
      if (selectedReviewItemIds.has(id)) selectedReviewItemIds.delete(id);
      else selectedReviewItemIds.add(id);
      return { selectedReviewItemIds };
    }),
  clearWorkspaceFocus: () =>
    set({
      focusedMissionId: null,
      highlightedMissionId: null,
      focusedPreviewItemId: null,
      panelMode: "closed",
      badgeCount: 0,
      evidenceQuery: "",
      selectedReviewItemIds: new Set<string>(),
      selectionRevision: null,
    }),
}));
