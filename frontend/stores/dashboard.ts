/**
 * Dashboard summary store for workspace cockpit surfaces.
 */

import { create } from "zustand";
import { getWorkspaceSummary, type WorkspaceSummaryData } from "@/lib/api";

interface DashboardState {
  summary: WorkspaceSummaryData | null;
  isLoading: boolean;
  error: string | null;
  fetchDashboard: (workspaceId: string) => Promise<void>;
  reset: () => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  summary: null,
  isLoading: false,
  error: null,

  fetchDashboard: async (workspaceId: string) => {
    set({ isLoading: true, error: null });
    try {
      const summary = await getWorkspaceSummary(workspaceId);
      set({
        summary,
        isLoading: false,
        error: null,
      });
    } catch (error) {
      set({
        summary: null,
        isLoading: false,
        error:
          error instanceof Error
            ? error.message
            : "Failed to load workspace summary",
      });
    }
  },

  reset: () => {
    set({
      summary: null,
      isLoading: false,
      error: null,
    });
  },
}));
