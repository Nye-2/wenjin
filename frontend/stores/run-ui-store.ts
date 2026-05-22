import { create } from "zustand";

interface RunUiState {
  activeRunId: string | null;
  focusedRunId: string | null;
  highlightedRunId: string | null;
  completedRunIds: Set<string>;
  markRunLaunching: (executionId: string) => void;
  markRunHydrated: (executionId: string, terminal?: boolean) => void;
  markRunCompleted: (executionId: string) => void;
  focusRun: (executionId: string | null) => void;
  highlightRunInDrawer: (executionId: string | null) => void;
  clearTerminalFocus: (executionId: string) => void;
  reset: () => void;
}

export const useRunUiStore = create<RunUiState>((set) => ({
  activeRunId: null,
  focusedRunId: null,
  highlightedRunId: null,
  completedRunIds: new Set<string>(),

  markRunLaunching(executionId) {
    set({
      activeRunId: executionId,
      focusedRunId: executionId,
      highlightedRunId: executionId,
    });
  },

  markRunHydrated(executionId, terminal = false) {
    set((state) => ({
      activeRunId: terminal ? state.activeRunId : executionId,
      focusedRunId: executionId,
      highlightedRunId: executionId,
    }));
  },

  markRunCompleted(executionId) {
    set((state) => {
      const completedRunIds = new Set(state.completedRunIds);
      completedRunIds.add(executionId);
      return {
        activeRunId: state.activeRunId === executionId ? null : state.activeRunId,
        focusedRunId: executionId,
        highlightedRunId: executionId,
        completedRunIds,
      };
    });
  },

  focusRun(executionId) {
    set({ focusedRunId: executionId });
  },

  highlightRunInDrawer(executionId) {
    set({ highlightedRunId: executionId });
  },

  clearTerminalFocus(executionId) {
    set((state) => ({
      activeRunId: state.activeRunId === executionId ? null : state.activeRunId,
      focusedRunId: state.focusedRunId === executionId ? null : state.focusedRunId,
    }));
  },

  reset() {
    set({
      activeRunId: null,
      focusedRunId: null,
      highlightedRunId: null,
      completedRunIds: new Set<string>(),
    });
  },
}));
