// frontend/stores/features.ts

import { create } from 'zustand';
import { getWorkspaceFeatures, getWorkspaceSkills, WorkspaceChatSkill, WorkspaceFeature } from '@/lib/api';

interface FeaturesState {
  features: WorkspaceFeature[];
  skills: WorkspaceChatSkill[];
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchFeatures: (workspaceId: string) => Promise<void>;
  getFeatureById: (featureId: string) => WorkspaceFeature | undefined;
  clearFeatures: () => void;
  fetchSkills: (workspaceId: string) => Promise<void>;
  getSkillById: (skillId: string) => WorkspaceChatSkill | undefined;
  clearSkills: () => void;
}

export const useFeaturesStore = create<FeaturesState>((set, get) => ({
  features: [],
  skills: [],
  isLoading: false,
  error: null,

  fetchFeatures: async (workspaceId: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await getWorkspaceFeatures(workspaceId);
      set({ features: response.features, isLoading: false });
    } catch (error) {
      set({
        error: (error as Error).message,
        isLoading: false,
        features: [],
      });
    }
  },

  getFeatureById: (featureId: string) => {
    return get().features.find((f) => f.id === featureId);
  },

  clearFeatures: () => {
    set({ features: [], skills: [], error: null });
  },

  fetchSkills: async (workspaceId: string) => {
    try {
      const data = await getWorkspaceSkills(workspaceId);
      set({ skills: data.skills });
    } catch (error) {
      console.error("Failed to fetch skills:", error);
    }
  },

  getSkillById: (skillId: string) => {
    return get().skills.find((s) => s.id === skillId);
  },

  clearSkills: () => set({ skills: [] }),
}));

export default useFeaturesStore;
