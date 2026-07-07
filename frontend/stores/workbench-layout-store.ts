import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type WorkbenchTab = "overview" | "spec" | "run" | "evidence" | "review";

interface WorkbenchLayoutState {
  splitRatio: number;
  isWorkbenchFullscreen: boolean;
  activeWorkbenchTab: WorkbenchTab;
  selectedRunId: string | null;
  selectedNodeId: string | null;
  setSplitRatio: (ratio: number) => void;
  resetSplitRatio: () => void;
  setWorkbenchFullscreen: (fullscreen: boolean) => void;
  toggleWorkbenchFullscreen: () => void;
  setActiveWorkbenchTab: (tab: WorkbenchTab) => void;
  setAutoWorkbenchTab: (tab: WorkbenchTab) => void;
  selectRun: (runId: string | null) => void;
  selectNode: (nodeId: string | null) => void;
  reset: () => void;
}

const DEFAULT_SPLIT_RATIO = 0.62;
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

      reset() {
        set({
          splitRatio: DEFAULT_SPLIT_RATIO,
          isWorkbenchFullscreen: false,
          activeWorkbenchTab: "overview",
          selectedRunId: null,
          selectedNodeId: null,
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
      }),
      merge: (persisted, current) => {
        const persistedState =
          persisted && typeof persisted === "object"
            ? (persisted as Partial<WorkbenchLayoutState>)
            : {};
        return {
          ...current,
          splitRatio:
            typeof persistedState.splitRatio === "number"
              ? clampSplitRatio(persistedState.splitRatio)
              : current.splitRatio,
          isWorkbenchFullscreen:
            typeof persistedState.isWorkbenchFullscreen === "boolean"
              ? persistedState.isWorkbenchFullscreen
              : current.isWorkbenchFullscreen,
          activeWorkbenchTab: isWorkbenchTab(persistedState.activeWorkbenchTab)
            ? persistedState.activeWorkbenchTab
            : current.activeWorkbenchTab,
          selectedRunId:
            typeof persistedState.selectedRunId === "string" ||
            persistedState.selectedRunId === null
              ? persistedState.selectedRunId
              : current.selectedRunId,
          selectedNodeId:
            typeof persistedState.selectedNodeId === "string" ||
            persistedState.selectedNodeId === null
              ? persistedState.selectedNodeId
              : current.selectedNodeId,
        };
      },
    },
  ),
);

function isWorkbenchTab(value: unknown): value is WorkbenchTab {
  return (
    value === "overview" ||
    value === "spec" ||
    value === "run" ||
    value === "evidence" ||
    value === "review"
  );
}
