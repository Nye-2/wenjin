// frontend/stores/features.ts

import { create } from 'zustand';
import { getWorkspaceFeatures, getWorkspaceSkills, WorkspaceThreadSkill, WorkspaceFeature } from '@/lib/api';

interface FeaturesState {
  activeWorkspaceId: string | null;
  featuresByWorkspace: Record<string, WorkspaceFeature[]>;
  skillsByWorkspace: Record<string, WorkspaceThreadSkill[]>;
  featureRequestIdByWorkspace: Record<string, string>;
  skillRequestIdByWorkspace: Record<string, string>;
  features: WorkspaceFeature[];
  skills: WorkspaceThreadSkill[];
  isLoading: boolean;
  error: string | null;

  // Actions
  setActiveWorkspace: (workspaceId: string | null) => void;
  fetchFeatures: (workspaceId: string) => Promise<void>;
  getFeatureById: (featureId: string) => WorkspaceFeature | undefined;
  clearFeatures: () => void;
  fetchSkills: (workspaceId: string) => Promise<void>;
  getSkillById: (skillId: string) => WorkspaceThreadSkill | undefined;
  clearSkills: () => void;
}

function normalizeWorkspaceId(value: string | null | undefined): string | null {
  const normalized = String(value ?? '').trim();
  return normalized || null;
}

function createRequestId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export const useFeaturesStore = create<FeaturesState>((set, get) => ({
  activeWorkspaceId: null,
  featuresByWorkspace: {},
  skillsByWorkspace: {},
  featureRequestIdByWorkspace: {},
  skillRequestIdByWorkspace: {},
  features: [],
  skills: [],
  isLoading: false,
  error: null,

  setActiveWorkspace: (workspaceId: string | null) => {
    const normalizedWorkspaceId = normalizeWorkspaceId(workspaceId);
    set((state) => ({
      activeWorkspaceId: normalizedWorkspaceId,
      features: normalizedWorkspaceId
        ? state.featuresByWorkspace[normalizedWorkspaceId] ?? []
        : [],
      skills: normalizedWorkspaceId
        ? state.skillsByWorkspace[normalizedWorkspaceId] ?? []
        : [],
      error: null,
    }));
  },

  fetchFeatures: async (workspaceId: string) => {
    const normalizedWorkspaceId = normalizeWorkspaceId(workspaceId);
    if (!normalizedWorkspaceId) {
      set({ isLoading: false, features: [], error: null });
      return;
    }

    const requestId = createRequestId();
    set((state) => ({
      activeWorkspaceId: normalizedWorkspaceId,
      features: state.featuresByWorkspace[normalizedWorkspaceId] ?? [],
      isLoading: true,
      error: null,
      featureRequestIdByWorkspace: {
        ...state.featureRequestIdByWorkspace,
        [normalizedWorkspaceId]: requestId,
      },
    }));

    try {
      const response = await getWorkspaceFeatures(normalizedWorkspaceId);
      set((state) => {
        if (state.featureRequestIdByWorkspace[normalizedWorkspaceId] !== requestId) {
          return state;
        }
        const featuresByWorkspace = {
          ...state.featuresByWorkspace,
          [normalizedWorkspaceId]: response.features,
        };
        const isActiveWorkspace = state.activeWorkspaceId === normalizedWorkspaceId;
        return {
          featuresByWorkspace,
          features: isActiveWorkspace ? response.features : state.features,
          isLoading: isActiveWorkspace ? false : state.isLoading,
          error: isActiveWorkspace ? null : state.error,
        };
      });
    } catch (error) {
      set((state) => {
        if (state.featureRequestIdByWorkspace[normalizedWorkspaceId] !== requestId) {
          return state;
        }
        if (state.activeWorkspaceId !== normalizedWorkspaceId) {
          return state;
        }
        return {
          error: (error as Error).message,
          isLoading: false,
          features: state.featuresByWorkspace[normalizedWorkspaceId] ?? [],
        };
      });
    }
  },

  getFeatureById: (featureId: string) => {
    return get().features.find((f) => f.id === featureId);
  },

  clearFeatures: () => {
    set({
      features: [],
      featuresByWorkspace: {},
      featureRequestIdByWorkspace: {},
      error: null,
      isLoading: false,
    });
  },

  fetchSkills: async (workspaceId: string) => {
    const normalizedWorkspaceId = normalizeWorkspaceId(workspaceId);
    if (!normalizedWorkspaceId) {
      set({ skills: [] });
      return;
    }

    const requestId = createRequestId();
    set((state) => ({
      activeWorkspaceId: normalizedWorkspaceId,
      skills: state.skillsByWorkspace[normalizedWorkspaceId] ?? [],
      skillRequestIdByWorkspace: {
        ...state.skillRequestIdByWorkspace,
        [normalizedWorkspaceId]: requestId,
      },
    }));

    try {
      const data = await getWorkspaceSkills(normalizedWorkspaceId);
      set((state) => {
        if (state.skillRequestIdByWorkspace[normalizedWorkspaceId] !== requestId) {
          return state;
        }
        const skillsByWorkspace = {
          ...state.skillsByWorkspace,
          [normalizedWorkspaceId]: data.skills,
        };
        return {
          skillsByWorkspace,
          skills:
            state.activeWorkspaceId === normalizedWorkspaceId
              ? data.skills
              : state.skills,
        };
      });
    } catch (error) {
      set((state) => {
        if (state.skillRequestIdByWorkspace[normalizedWorkspaceId] !== requestId) {
          return state;
        }
        if (state.activeWorkspaceId !== normalizedWorkspaceId) {
          return state;
        }
        return {
          skills: state.skillsByWorkspace[normalizedWorkspaceId] ?? [],
          error: (error as Error).message,
        };
      });
    }
  },

  getSkillById: (skillId: string) => {
    return get().skills.find((s) => s.id === skillId);
  },

  clearSkills: () =>
    set({
      skills: [],
      skillsByWorkspace: {},
      skillRequestIdByWorkspace: {},
    }),
}));

export default useFeaturesStore;
