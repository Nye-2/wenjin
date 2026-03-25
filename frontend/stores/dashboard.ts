/**
 * Dashboard store for workspace module status
 */

import { create } from "zustand";
import {
  getWorkspaceDashboard,
  getWorkspaceSummary,
  type ModuleStatus,
  type WorkspaceSummaryData,
} from "@/lib/api";

// Re-export for convenience
export type { ModuleStatus };

interface RecentArtifact {
  id: string;
  type: string;
  title: string | null;
  created_at: string;
}

interface DashboardState {
  modules: ModuleStatus[];
  recentArtifacts: RecentArtifact[];
  summary: WorkspaceSummaryData | null;
  isLoading: boolean;
  error: string | null;
  fetchDashboard: (workspaceId: string) => Promise<void>;
  reset: () => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  modules: [],
  recentArtifacts: [],
  summary: null,
  isLoading: false,
  error: null,

  fetchDashboard: async (workspaceId: string) => {
    set({ isLoading: true, error: null });
    const [dashboardResult, summaryResult] = await Promise.allSettled([
      getWorkspaceDashboard(workspaceId),
      getWorkspaceSummary(workspaceId),
    ]);

    if (dashboardResult.status === "fulfilled") {
      const data = dashboardResult.value;
      set({
        modules: data.modules || [],
        recentArtifacts: data.recent_artifacts || [],
      });
    }

    if (summaryResult.status === "fulfilled") {
      set({ summary: summaryResult.value });
    }

    const dashboardError =
      dashboardResult.status === "rejected"
        ? dashboardResult.reason instanceof Error
          ? dashboardResult.reason.message
          : "Failed to load dashboard"
        : null;
    const summaryError =
      summaryResult.status === "rejected"
        ? summaryResult.reason instanceof Error
          ? summaryResult.reason.message
          : "Failed to load workspace summary"
        : null;

    set({
      isLoading: false,
      error: dashboardError || summaryError,
      ...(dashboardResult.status === "rejected"
        ? { modules: [], recentArtifacts: [] }
        : {}),
      ...(summaryResult.status === "rejected" ? { summary: null } : {}),
    });
  },

  reset: () => {
    set({
      modules: [],
      recentArtifacts: [],
      summary: null,
      isLoading: false,
      error: null,
    });
  },
}));
