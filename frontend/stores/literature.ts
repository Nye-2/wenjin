/**
 * Literature store for managing workspace references
 */

import { create } from "zustand";
import {
  listLiterature,
  createLiterature,
  updateLiterature,
  deleteLiterature,
  importLiterature,
  type Literature,
} from "@/lib/api";

interface LiteratureState {
  items: Literature[];
  total: number;
  coreCount: number;
  isLoading: boolean;
  error: string | null;
  fetchLiterature: (
    workspaceId: string,
    filters?: { source?: string; is_core?: boolean }
  ) => Promise<void>;
  addLiterature: (
    workspaceId: string,
    data: Partial<Literature>
  ) => Promise<Literature | null>;
  toggleCore: (
    workspaceId: string,
    litId: string,
    isCore: boolean
  ) => Promise<void>;
  removeLiterature: (workspaceId: string, litId: string) => Promise<void>;
  importFromDeepResearch: (
    workspaceId: string,
    paperIds: string[]
  ) => Promise<number>;
  reset: () => void;
}

export const useLiteratureStore = create<LiteratureState>((set, get) => ({
  items: [],
  total: 0,
  coreCount: 0,
  isLoading: false,
  error: null,

  fetchLiterature: async (workspaceId, filters?) => {
    set({ isLoading: true, error: null });
    try {
      const data = await listLiterature(workspaceId, filters);
      set({
        items: data.items || [],
        total: data.total || 0,
        coreCount: data.core_count || 0,
        isLoading: false,
      });
    } catch (e: unknown) {
      const error = e instanceof Error ? e.message : "Failed to load literature";
      set({ error, isLoading: false });
    }
  },

  addLiterature: async (workspaceId, data) => {
    try {
      const lit = await createLiterature(workspaceId, {
        title: data.title || "",
        authors: (data.authors as string[]) || [],
        year: data.year ?? undefined,
        doi: data.doi ?? undefined,
        venue: data.venue ?? undefined,
        quartile: data.quartile ?? undefined,
        abstract: data.abstract ?? undefined,
        citations: data.citations ?? undefined,
        source: data.source || "manual",
      });
      await get().fetchLiterature(workspaceId);
      return lit;
    } catch (e: unknown) {
      const error = e instanceof Error ? e.message : "Failed to add literature";
      set({ error });
      return null;
    }
  },

  toggleCore: async (workspaceId, litId, isCore) => {
    try {
      await updateLiterature(workspaceId, litId, { is_core: isCore });
      await get().fetchLiterature(workspaceId);
    } catch (e: unknown) {
      const error = e instanceof Error ? e.message : "Failed to update";
      set({ error });
    }
  },

  removeLiterature: async (workspaceId, litId) => {
    try {
      await deleteLiterature(workspaceId, litId);
      await get().fetchLiterature(workspaceId);
    } catch (e: unknown) {
      const error = e instanceof Error ? e.message : "Failed to delete";
      set({ error });
    }
  },

  importFromDeepResearch: async (workspaceId, paperIds) => {
    try {
      const result = await importLiterature(workspaceId, {
        source: "deep_research",
        paper_ids: paperIds,
      });
      await get().fetchLiterature(workspaceId);
      return result.imported;
    } catch (e: unknown) {
      const error = e instanceof Error ? e.message : "Failed to import";
      set({ error });
      return 0;
    }
  },

  reset: () => {
    set({
      items: [],
      total: 0,
      coreCount: 0,
      isLoading: false,
      error: null,
    });
  },
}));

export type { Literature };
