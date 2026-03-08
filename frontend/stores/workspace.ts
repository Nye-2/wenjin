/**
 * Workspace Store for AcademiaGPT
 * Manages workspace, artifacts, and papers state
 */

import { create } from 'zustand';
import {
  getWorkspace,
  listWorkspacePapers,
  listArtifacts,
  createArtifact,
  createPaper as apiCreatePaper,
} from '../lib/api';

// ============ Types ============

export interface Workspace {
  id: string;
  name: string;
  type: 'sci' | 'thesis' | 'proposal' | 'grant';
  discipline: string | null;
  description: string | null;
  created_at: string;
}

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
  workspace: Workspace | null;
  artifacts: Artifact[];
  papers: Paper[];
  isLoading: boolean;
  error: string | null;

  // Actions
  loadWorkspace: (id: string) => Promise<void>;
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
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  workspace: null,
  artifacts: [],
  papers: [],
  isLoading: false,
  error: null,

  loadWorkspace: async (id: string) => {
    set({ isLoading: true, error: null });
    try {
      const workspace = await getWorkspace(id);
      set({ workspace: workspace as unknown as Workspace, isLoading: false });

      // Also load papers and artifacts for this workspace
      const [papersResponse, artifactsResponse] = await Promise.all([
        listWorkspacePapers(id),
        listArtifacts(id),
      ]);

      set({
        papers: papersResponse.papers.map((p) => ({
          id: p.id,
          title: p.title,
          authors: p.authors?.map((a) => a.name) || [],
          year: p.year || null,
          venue: p.venue || null,
        })),
        artifacts: artifactsResponse.artifacts.map((a) => ({
          id: a.id,
          workspace_id: a.workspace_id,
          type: a.type,
          title: a.title || null,
          content: a.content,
          created_at: a.created_at,
        })),
      });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
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
      error: null,
    });
  },

  fetchPapers: async (workspaceId: string) => {
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
      });
    } catch (error) {
      set({ error: (error as Error).message });
    }
  },

  fetchArtifacts: async (workspaceId: string) => {
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
      });
    } catch (error) {
      set({ error: (error as Error).message });
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
}));

export default useWorkspaceStore;
