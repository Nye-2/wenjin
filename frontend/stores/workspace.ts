/**
 * Workspace Store for AcademiaGPT
 * Manages workspace list, details, artifacts, and papers state
 */

import { create } from 'zustand';
import {
  Workspace as ApiWorkspace,
  WorkspaceCreate,
  listWorkspaces,
  getWorkspace,
  listWorkspacePapers,
  listArtifacts,
  createArtifact,
  createWorkspace as apiCreateWorkspace,
  deleteWorkspace as apiDeleteWorkspace,
} from '../lib/api';

// ============ Types ============

export type Workspace = ApiWorkspace;

export interface Artifact {
  id: string;
  workspace_id: string;
  type: string;
  title: string | null;
  content: Record<string, unknown>;
  created_at: string;
}

export interface Paper {
  id: string;
  title: string;
  authors: string[];
  year: number | null;
  venue: string | null;
}

// ============ Store State ============

interface WorkspaceState {
  workspaces: Workspace[];
  workspace: Workspace | null;
  artifacts: Artifact[];
  papers: Paper[];
  isWorkspacesLoading: boolean;
  isWorkspaceLoading: boolean;
  isPapersLoading: boolean;
  isArtifactsLoading: boolean;
  isWorkspaceMutating: boolean;
  error: string | null;

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
  createArtifact: (data: {
    workspace_id: string;
    type: string;
    title?: string;
    content: Record<string, unknown>;
  }) => Promise<Artifact>;
  clearError: () => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  workspaces: [],
  workspace: null,
  artifacts: [],
  papers: [],
  isWorkspacesLoading: false,
  isWorkspaceLoading: false,
  isPapersLoading: false,
  isArtifactsLoading: false,
  isWorkspaceMutating: false,
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
    set({ isWorkspaceLoading: true, error: null });
    try {
      const workspace = await getWorkspace(id);
      set({
        workspace,
        isWorkspaceLoading: false,
      });
    } catch (error) {
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
      isWorkspaceLoading: false,
      isPapersLoading: false,
      isArtifactsLoading: false,
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
          created_at: a.created_at,
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

  createArtifact: async (data) => {
    try {
      const artifact = await createArtifact({
        workspace_id: data.workspace_id,
        type: data.type,
        title: data.title,
        content: data.content,
      });
      const mappedArtifact: Artifact = {
        id: artifact.id,
        workspace_id: artifact.workspace_id,
        type: artifact.type,
        title: artifact.title || null,
        content: artifact.content,
        created_at: artifact.created_at,
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
}));

export default useWorkspaceStore;
