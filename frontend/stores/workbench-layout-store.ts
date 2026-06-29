import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type WorkbenchTab = "overview" | "spec" | "run" | "evidence" | "review";

export type WorkbenchDraftEdit = {
  data?: Record<string, unknown>;
  preview?: string;
};

interface WorkbenchLayoutState {
  splitRatio: number;
  isWorkbenchFullscreen: boolean;
  activeWorkbenchTab: WorkbenchTab;
  selectedRunId: string | null;
  selectedNodeId: string | null;
  draftEdits: Record<string, WorkbenchDraftEdit>;
  setSplitRatio: (ratio: number) => void;
  resetSplitRatio: () => void;
  setWorkbenchFullscreen: (fullscreen: boolean) => void;
  toggleWorkbenchFullscreen: () => void;
  setActiveWorkbenchTab: (tab: WorkbenchTab) => void;
  setAutoWorkbenchTab: (tab: WorkbenchTab) => void;
  selectRun: (runId: string | null) => void;
  selectNode: (nodeId: string | null) => void;
  setDraftEdit: (outputId: string, edit: WorkbenchDraftEdit | null) => void;
  patchDraftData: (outputId: string, field: string, value: unknown) => void;
  clearDraftEdits: (outputIds?: string[]) => void;
  reset: () => void;
}

const DEFAULT_SPLIT_RATIO = 0.42;
const MIN_SPLIT_RATIO = 0.28;
const MAX_SPLIT_RATIO = 0.72;

function clampSplitRatio(ratio: number): number {
  if (!Number.isFinite(ratio)) {
    return DEFAULT_SPLIT_RATIO;
  }
  return Math.min(MAX_SPLIT_RATIO, Math.max(MIN_SPLIT_RATIO, ratio));
}

export const useWorkbenchLayoutStore = create<WorkbenchLayoutState>()(
  persist(
    (set) => ({
      splitRatio: DEFAULT_SPLIT_RATIO,
      isWorkbenchFullscreen: false,
      activeWorkbenchTab: "overview",
      selectedRunId: null,
      selectedNodeId: null,
      draftEdits: {},

      setSplitRatio(ratio) {
        set({ splitRatio: clampSplitRatio(ratio) });
      },

      resetSplitRatio() {
        set({ splitRatio: DEFAULT_SPLIT_RATIO });
      },

      setWorkbenchFullscreen(fullscreen) {
        set({ isWorkbenchFullscreen: fullscreen });
      },

      toggleWorkbenchFullscreen() {
        set((state) => ({
          isWorkbenchFullscreen: !state.isWorkbenchFullscreen,
        }));
      },

      setActiveWorkbenchTab(tab) {
        set({ activeWorkbenchTab: tab });
      },

      setAutoWorkbenchTab(tab) {
        set({ activeWorkbenchTab: tab });
      },

      selectRun(runId) {
        set({ selectedRunId: runId });
      },

      selectNode(nodeId) {
        set({ selectedNodeId: nodeId });
      },

      setDraftEdit(outputId, edit) {
        set((state) => {
          const draftEdits = { ...state.draftEdits };
          if (!edit || (!edit.preview && !edit.data)) {
            delete draftEdits[outputId];
          } else {
            draftEdits[outputId] = edit;
          }
          return { draftEdits };
        });
      },

      patchDraftData(outputId, field, value) {
        set((state) => ({
          draftEdits: {
            ...state.draftEdits,
            [outputId]: {
              ...(state.draftEdits[outputId] ?? {}),
              data: {
                ...(state.draftEdits[outputId]?.data ?? {}),
                [field]: value,
              },
            },
          },
        }));
      },

      clearDraftEdits(outputIds) {
        set((state) => {
          if (!outputIds) {
            return { draftEdits: {} };
          }
          const draftEdits = { ...state.draftEdits };
          for (const outputId of outputIds) {
            delete draftEdits[outputId];
          }
          return { draftEdits };
        });
      },

      reset() {
        set({
          splitRatio: DEFAULT_SPLIT_RATIO,
          isWorkbenchFullscreen: false,
          activeWorkbenchTab: "overview",
          selectedRunId: null,
          selectedNodeId: null,
          draftEdits: {},
        });
      },
    }),
    {
      name: "wenjin-workbench-layout",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        splitRatio: state.splitRatio,
        isWorkbenchFullscreen: state.isWorkbenchFullscreen,
        activeWorkbenchTab: state.activeWorkbenchTab,
        selectedRunId: state.selectedRunId,
        selectedNodeId: state.selectedNodeId,
        draftEdits: state.draftEdits,
      }),
    },
  ),
);
