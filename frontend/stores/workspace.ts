/**
 * Workspace Store for Wenjin (问津)
 * Manages workspace list, details, artifacts, and reference-library state
 */

import { create } from 'zustand';
import {
  Workspace as ApiWorkspace,
  WorkspaceActivityItem as ApiWorkspaceActivityItem,
  WorkspaceCreate,
  WorkspaceReference as ApiWorkspaceReference,
  listWorkspaces,
  getWorkspace,
  listWorkspaceReferences,
  listArtifacts,
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

export type Reference = ApiWorkspaceReference;

export type WorkspaceActivityItem = ApiWorkspaceActivityItem;

// ============ Store State ============

interface WorkspaceState {
  workspaces: Workspace[];
  workspace: Workspace | null;
  artifacts: Artifact[];
  references: Reference[];
  activities: WorkspaceActivityItem[];
  isWorkspacesLoading: boolean;
  isWorkspaceLoading: boolean;
  isReferencesLoading: boolean;
  isArtifactsLoading: boolean;
  isActivityLoading: boolean;
  isWorkspaceMutating: boolean;
  error: string | null;
  workspaceNotFound: boolean;
  _lastLoadRequestId: string | null;

  // Actions
  fetchWorkspaces: () => Promise<void>;
  loadWorkspace: (id: string) => Promise<void>;
  createWorkspace: (data: WorkspaceCreate) => Promise<Workspace>;
  removeWorkspace: (id: string) => Promise<void>;
  addReference: (reference: Reference) => void;
  addArtifact: (artifact: Artifact) => void;
  setWorkspace: (workspace: Workspace | null) => void;
  clearWorkspace: () => void;
  fetchReferences: (workspaceId: string) => Promise<void>;
  fetchArtifacts: (workspaceId: string) => Promise<void>;
  fetchActivity: (workspaceId: string, limit?: number) => Promise<void>;
  upsertActivity: (activity: WorkspaceActivityItem) => void;
  removeActivity: (activityId: string) => void;

  clearError: () => void;
  isThreadCockpitEnabled: () => boolean;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  workspaces: [],
  workspace: null,
  artifacts: [],
  references: [],
  activities: [],
  isWorkspacesLoading: false,
  isWorkspaceLoading: false,
  isReferencesLoading: false,
  isArtifactsLoading: false,
  isActivityLoading: false,
  isWorkspaceMutating: false,
  workspaceNotFound: false,
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
    set({
      isWorkspaceLoading: true,
      error: null,
      workspaceNotFound: false,
      _lastLoadRequestId: requestId,
    });
    try {
      const workspace = await getWorkspace(id);
      const current = get()._lastLoadRequestId;
      if (current !== requestId) return;
      set({
        workspace,
        isWorkspaceLoading: false,
      });
    } catch (error) {
      const current = get()._lastLoadRequestId;
      if (current !== requestId) return;
      // Distinguish "workspace does not exist" (4xx) from transient errors so
      // the layout can redirect away instead of hammering retry endpoints
      // for a non-existent id (e.g. a stale ``/workspaces/v2`` tab).
      const status =
        typeof error === "object" && error !== null && "response" in error
          ? ((error as { response?: { status?: number } }).response?.status ?? 0)
          : 0;
      const notFound = status === 404 || status === 403 || status === 410;
      set({
        error: (error as Error).message,
        isWorkspaceLoading: false,
        workspaceNotFound: notFound,
      });
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

  addReference: (reference: Reference) => {
    set((state) => ({
      references: [...state.references, reference],
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
      references: [],
      activities: [],
      isWorkspaceLoading: false,
      isReferencesLoading: false,
      isArtifactsLoading: false,
      isActivityLoading: false,
      workspaceNotFound: false,
    });
  },

  fetchReferences: async (workspaceId: string) => {
    set({ isReferencesLoading: true, error: null });
    try {
      const response = await listWorkspaceReferences(workspaceId, {
        limit: 200,
      });
      set({
        references: response.items,
        isReferencesLoading: false,
      });
    } catch (error) {
      set({
        error: (error as Error).message,
        isReferencesLoading: false,
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

  clearError: () => {
    set({ error: null });
  },

  isThreadCockpitEnabled: () => {
    return isWorkspaceThreadCockpitEnabled(get().workspace);
  },
}));

export default useWorkspaceStore;
