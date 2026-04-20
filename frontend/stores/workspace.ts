/**
 * Workspace Store for Wenjin (问津)
 * Manages workspace list, details, artifacts, and papers state
 */

import { create } from 'zustand';
import {
  Workspace as ApiWorkspace,
  WorkspaceActivityItem as ApiWorkspaceActivityItem,
  WorkspaceCreate,
  listWorkspaces,
  getWorkspace,
  listWorkspacePapers,
  listArtifacts,
  createArtifact,
  createWorkspace as apiCreateWorkspace,
  deleteWorkspace as apiDeleteWorkspace,
  getWorkspaceActivity,
} from '../lib/api';
import {
  isWorkspaceThreadCockpitEnabled,
} from '@/lib/workspace-rollout';
import { upsertWorkspaceActivityList } from '@/lib/workspace-event-ordering';

// ============ Types ============

export type Workspace = ApiWorkspace;

export interface Artifact {
  id: string;
  workspace_id: string;
  type: string;
  title: string | null;
  content: Record<string, unknown>;
  created_by_skill?: string | null;
  parent_artifact_id?: string | null;
  version?: number;
  status?: string;
  created_at: string;
  updated_at?: string;
}

export interface Paper {
  id: string;
  title: string;
  authors: string[];
  year: number | null;
  venue: string | null;
  file_url?: string | null;
}

export type WorkspaceActivityItem = ApiWorkspaceActivityItem;

// ============ Store State ============

interface WorkspaceState {
  workspaces: Workspace[];
  workspace: Workspace | null;
  artifacts: Artifact[];
  papers: Paper[];
  activities: WorkspaceActivityItem[];
  isWorkspacesLoading: boolean;
  isWorkspaceLoading: boolean;
  isPapersLoading: boolean;
  isArtifactsLoading: boolean;
  isActivityLoading: boolean;
  isWorkspaceMutating: boolean;
  error: string | null;
  _lastLoadRequestId: string | null;

  // Actions
  fetchWorkspaces: () => Promise<void>;
  loadWorkspace: (id: string) => Promise<void>;
  createWorkspace: (data: WorkspaceCreate) => Promise<Workspace>;
  removeWorkspace: (id: string) => Promise<void>;
  addPaper: (paper: Paper) => void;
  addArtifact: (artifact: Artifact) => void;
  setWorkspace: (workspace: Workspace | null) => void;
  clearWorkspace: () => void;
  fetchPapers: (workspaceId: string) => Promise<void>;
  fetchArtifacts: (workspaceId: string) => Promise<void>;
  fetchActivity: (workspaceId: string, limit?: number) => Promise<void>;
  upsertActivity: (activity: WorkspaceActivityItem) => void;
  removeActivity: (activityId: string) => void;
  createArtifact: (data: {
    workspace_id: string;
    type: string;
    title?: string;
    content: Record<string, unknown>;
    created_by_skill?: string;
    parent_artifact_id?: string;
  }) => Promise<Artifact>;
  clearError: () => void;
  isThreadCockpitEnabled: () => boolean;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  workspaces: [],
  workspace: null,
  artifacts: [],
  papers: [],
  activities: [],
  isWorkspacesLoading: false,
  isWorkspaceLoading: false,
  isPapersLoading: false,
  isArtifactsLoading: false,
  isActivityLoading: false,
  isWorkspaceMutating: false,
  _lastLoadRequestId: null as string | null,
  error: null,

  fetchWorkspaces: async () => {
    set({ isWorkspacesLoading: true, error: null });
    try {
      const response = await listWorkspaces();
      set({
        workspaces: response.workspaces,
        isWorkspacesLoading: false,
      });
    } catch (error) {
      set({
        error: (error as Error).message,
        isWorkspacesLoading: false,
      });
    }
  },

  loadWorkspace: async (id: string) => {
    const requestId = crypto.randomUUID();
    set({ isWorkspaceLoading: true, error: null, _lastLoadRequestId: requestId });
    try {
      const workspace = await getWorkspace(id);
      // Only apply if this is still the latest request
      const current = get()._lastLoadRequestId;
      if (current !== requestId) return;
      set({
        workspace,
        isWorkspaceLoading: false,
      });
    } catch (error) {
      const current = get()._lastLoadRequestId;
      if (current !== requestId) return;
      set({ error: (error as Error).message, isWorkspaceLoading: false });
    }
  },

  createWorkspace: async (data) => {
    set({ isWorkspaceMutating: true, error: null });
    try {
      const workspace = await apiCreateWorkspace(data);
      set((state) => ({
        workspaces: [...state.workspaces, workspace],
        isWorkspaceMutating: false,
      }));
      return workspace;
    } catch (error) {
      set({
        error: (error as Error).message,
        isWorkspaceMutating: false,
      });
      throw error;
    }
  },

  removeWorkspace: async (id) => {
    set({ isWorkspaceMutating: true, error: null });
    try {
      await apiDeleteWorkspace(id);
      set((state) => ({
        workspaces: state.workspaces.filter((workspace) => workspace.id !== id),
        workspace: state.workspace?.id === id ? null : state.workspace,
        isWorkspaceMutating: false,
      }));
    } catch (error) {
      set({
        error: (error as Error).message,
        isWorkspaceMutating: false,
      });
      throw error;
    }
  },

  addPaper: (paper: Paper) => {
    set((state) => ({
      papers: [...state.papers, paper],
    }));
  },

  addArtifact: (artifact: Artifact) => {
    set((state) => ({
      artifacts: [...state.artifacts, artifact],
    }));
  },

  setWorkspace: (workspace: Workspace | null) => {
    set({ workspace });
  },

  clearWorkspace: () => {
    set({
      workspace: null,
      artifacts: [],
      papers: [],
      activities: [],
      isWorkspaceLoading: false,
      isPapersLoading: false,
      isArtifactsLoading: false,
      isActivityLoading: false,
    });
  },

  fetchPapers: async (workspaceId: string) => {
    set({ isPapersLoading: true, error: null });
    try {
      const response = await listWorkspacePapers(workspaceId);
      set({
        papers: response.papers.map((p) => ({
          id: p.id,
          title: p.title,
          authors: p.authors?.map((a) => a.name) || [],
          year: p.year || null,
          venue: p.venue || null,
          file_url: p.file_url ?? null,
        })),
        isPapersLoading: false,
      });
    } catch (error) {
      set({
        error: (error as Error).message,
        isPapersLoading: false,
      });
    }
  },

  fetchArtifacts: async (workspaceId: string) => {
    set({ isArtifactsLoading: true, error: null });
    try {
      const response = await listArtifacts(workspaceId);
      set({
        artifacts: response.artifacts.map((a) => ({
          id: a.id,
          workspace_id: a.workspace_id,
          type: a.type,
          title: a.title || null,
          content: a.content,
          created_by_skill: a.created_by_skill ?? null,
          parent_artifact_id: a.parent_artifact_id ?? null,
          version: a.version,
          status: a.status,
          created_at: a.created_at,
          updated_at: a.updated_at,
        })),
        isArtifactsLoading: false,
      });
    } catch (error) {
      set({
        error: (error as Error).message,
        isArtifactsLoading: false,
      });
    }
  },

  fetchActivity: async (workspaceId: string, limit: number = 40) => {
    set({ isActivityLoading: true, error: null });
    try {
      const response = await getWorkspaceActivity(workspaceId, limit);
      set({
        activities: response.items,
        isActivityLoading: false,
      });
    } catch (error) {
      set({
        error: (error as Error).message,
        isActivityLoading: false,
      });
    }
  },

  upsertActivity: (activity: WorkspaceActivityItem) => {
    if (!activity?.id) {
      return;
    }

    set((state) => {
      const limit = state.activities.length > 0 ? state.activities.length : 40;
      return {
        activities: upsertWorkspaceActivityList(state.activities, activity, limit),
      };
    });
  },

  removeActivity: (activityId: string) => {
    if (!activityId) {
      return;
    }

    set((state) => ({
      activities: state.activities.filter((item) => item.id !== activityId),
    }));
  },

  createArtifact: async (data) => {
    try {
      const artifact = await createArtifact({
        workspace_id: data.workspace_id,
        type: data.type,
        title: data.title,
        content: data.content,
        created_by_skill: data.created_by_skill,
        parent_artifact_id: data.parent_artifact_id,
      });
      const mappedArtifact: Artifact = {
        id: artifact.id,
        workspace_id: artifact.workspace_id,
        type: artifact.type,
        title: artifact.title || null,
        content: artifact.content,
        created_by_skill: artifact.created_by_skill ?? null,
        parent_artifact_id: artifact.parent_artifact_id ?? null,
        version: artifact.version,
        status: artifact.status,
        created_at: artifact.created_at,
        updated_at: artifact.updated_at,
      };
      get().addArtifact(mappedArtifact);
      return mappedArtifact;
    } catch (error) {
      set({ error: (error as Error).message });
      throw error;
    }
  },

  clearError: () => {
    set({ error: null });
  },

  isThreadCockpitEnabled: () => {
    return isWorkspaceThreadCockpitEnabled(get().workspace);
  },
}));

export default useWorkspaceStore;
