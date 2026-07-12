import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

interface WorkbenchLayoutState {
  splitRatio: number;
  isWorkbenchFullscreen: boolean;
  setSplitRatio: (ratio: number) => void;
  resetSplitRatio: () => void;
  setWorkbenchFullscreen: (fullscreen: boolean) => void;
  toggleWorkbenchFullscreen: () => void;
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

      reset() {
        set({
          splitRatio: DEFAULT_SPLIT_RATIO,
          isWorkbenchFullscreen: false,
        });
      },
    }),
    {
      name: "wenjin-workbench-layout",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        splitRatio: state.splitRatio,
        isWorkbenchFullscreen: state.isWorkbenchFullscreen,
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
        };
      },
    },
  ),
);
