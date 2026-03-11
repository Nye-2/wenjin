// frontend/stores/features.ts

import { create } from 'zustand';
import { getWorkspaceFeatures, WorkspaceFeature } from '@/lib/api';

interface FeaturesState {
  features: WorkspaceFeature[];
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchFeatures: (workspaceId: string) => Promise<void>;
  getFeatureById: (featureId: string) => WorkspaceFeature | undefined;
  clearFeatures: () => void;
}

export const useFeaturesStore = create<FeaturesState>((set, get) => ({
  features: [],
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
    set({ features: [], error: null });
  },
}));

export default useFeaturesStore;
