/**
 * Dashboard store for workspace module status
 */

import { create } from "zustand";
import { getWorkspaceDashboard } from "@/lib/api";

export interface ModuleStatus {
  id: string;
  status: "not_started" | "in_progress" | "completed";
  summary: Record<string, unknown>;
}

interface RecentArtifact {
  id: string;
  type: string;
  title: string | null;
  created_at: string;
}

interface DashboardState {
  modules: ModuleStatus[];
  recentArtifacts: RecentArtifact[];
  isLoading: boolean;
  error: string | null;
  fetchDashboard: (workspaceId: string) => Promise<void>;
  reset: () => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  modules: [],
  recentArtifacts: [],
  isLoading: false,
  error: null,

  fetchDashboard: async (workspaceId: string) => {
    set({ isLoading: true, error: null });
    try {
      const data = await getWorkspaceDashboard(workspaceId);
      set({
        modules: data.modules || [],
        recentArtifacts: data.recent_artifacts || [],
        isLoading: false,
      });
    } catch (e: unknown) {
      const error = e instanceof Error ? e.message : "Failed to load dashboard";
      set({ error, isLoading: false });
    }
  },

  reset: () => {
    set({ modules: [], recentArtifacts: [], isLoading: false, error: null });
  },
}));
