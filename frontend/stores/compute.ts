import { create } from "zustand";

import {
  getComputeProjection,
  getWorkspaceComputeSessions,
  type ComputeProjection,
  type ComputeSession,
} from "@/lib/api";

interface ComputeStoreState {
  byWorkspace: Record<string, ComputeSession[]>;
  projectionBySessionId: Record<string, ComputeProjection>;
  activeComputeSessionIdByWorkspace: Record<string, string | null>;
  isLoadingByWorkspace: Record<string, boolean>;
  isProjectionLoadingBySessionId: Record<string, boolean>;
  hydrateWorkspace: (workspaceId: string, limit?: number) => Promise<void>;
  fetchProjection: (computeSessionId: string) => Promise<ComputeProjection | null>;
  upsertComputeSession: (workspaceId: string, session: ComputeSession) => void;
  setActiveComputeSession: (
    workspaceId: string,
    computeSessionId: string | null
  ) => void;
  clearWorkspace: (workspaceId: string) => void;
}

function normalizeComputeSession(
  session: ComputeSession,
  previous?: ComputeSession | null
): ComputeSession {
  return {
    ...previous,
    ...session,
    ui_state: session.ui_state ?? previous?.ui_state ?? {},
  };
}

function upsertSessionList(
  items: ComputeSession[],
  session: ComputeSession
): ComputeSession[] {
  const existing = items.find((item) => item.id === session.id);
  const nextSession = normalizeComputeSession(session, existing);
  if (
    existing &&
    existing.updated_at === nextSession.updated_at &&
    existing.execution_session_id === nextSession.execution_session_id &&
    existing.active_view === nextSession.active_view &&
    existing.sandbox_session_id === nextSession.sandbox_session_id &&
    existing.ui_state === nextSession.ui_state
  ) {
    return items;
  }
  const next = [nextSession, ...items.filter((item) => item.id !== nextSession.id)];
  next.sort((left, right) =>
    String(right.updated_at || right.created_at || "").localeCompare(
      String(left.updated_at || left.created_at || "")
    )
  );
  return next;
}

function selectPreferredComputeSessionId(items: ComputeSession[]): string | null {
  return items[0]?.id ?? null;
}

export const useComputeStore = create<ComputeStoreState>((set, get) => ({
  byWorkspace: {},
  projectionBySessionId: {},
  activeComputeSessionIdByWorkspace: {},
  isLoadingByWorkspace: {},
  isProjectionLoadingBySessionId: {},

  hydrateWorkspace: async (workspaceId, limit = 20) => {
    set((state) => ({
      isLoadingByWorkspace: {
        ...state.isLoadingByWorkspace,
        [workspaceId]: true,
      },
    }));

    try {
      const response = await getWorkspaceComputeSessions(workspaceId, limit);
      set((state) => {
        const items = response.items.map((item) => normalizeComputeSession(item));
        const currentActiveId =
          state.activeComputeSessionIdByWorkspace[workspaceId] ?? null;
        const nextActiveId =
          currentActiveId && items.some((item) => item.id === currentActiveId)
            ? currentActiveId
            : selectPreferredComputeSessionId(items);
        return {
          byWorkspace: {
            ...state.byWorkspace,
            [workspaceId]: items,
          },
          activeComputeSessionIdByWorkspace: {
            ...state.activeComputeSessionIdByWorkspace,
            [workspaceId]: nextActiveId,
          },
          isLoadingByWorkspace: {
            ...state.isLoadingByWorkspace,
            [workspaceId]: false,
          },
        };
      });
    } catch {
      set((state) => ({
        isLoadingByWorkspace: {
          ...state.isLoadingByWorkspace,
          [workspaceId]: false,
        },
      }));
    }
  },

  fetchProjection: async (computeSessionId) => {
    set((state) => ({
      isProjectionLoadingBySessionId: {
        ...state.isProjectionLoadingBySessionId,
        [computeSessionId]: true,
      },
    }));

    try {
      const projection = await getComputeProjection(computeSessionId);
      set((state) => ({
        projectionBySessionId: {
          ...state.projectionBySessionId,
          [computeSessionId]: projection,
        },
        isProjectionLoadingBySessionId: {
          ...state.isProjectionLoadingBySessionId,
          [computeSessionId]: false,
        },
      }));
      return projection;
    } catch {
      set((state) => ({
        isProjectionLoadingBySessionId: {
          ...state.isProjectionLoadingBySessionId,
          [computeSessionId]: false,
        },
      }));
      return null;
    }
  },

  upsertComputeSession: (workspaceId, session) => {
    set((state) => {
      const items = upsertSessionList(state.byWorkspace[workspaceId] ?? [], session);
      const currentActiveId =
        state.activeComputeSessionIdByWorkspace[workspaceId] ?? null;
      return {
        byWorkspace: {
          ...state.byWorkspace,
          [workspaceId]: items,
        },
        activeComputeSessionIdByWorkspace: {
          ...state.activeComputeSessionIdByWorkspace,
          [workspaceId]:
            currentActiveId && items.some((item) => item.id === currentActiveId)
              ? currentActiveId
              : session.id,
        },
      };
    });
  },

  setActiveComputeSession: (workspaceId, computeSessionId) => {
    set((state) => ({
      activeComputeSessionIdByWorkspace: {
        ...state.activeComputeSessionIdByWorkspace,
        [workspaceId]: computeSessionId,
      },
    }));
    if (computeSessionId) {
      void get().fetchProjection(computeSessionId);
    }
  },

  clearWorkspace: (workspaceId) => {
    set((state) => {
      const nextByWorkspace = { ...state.byWorkspace };
      const nextActive = { ...state.activeComputeSessionIdByWorkspace };
      const nextLoading = { ...state.isLoadingByWorkspace };
      const nextProjectionBySessionId = { ...state.projectionBySessionId };
      const sessions = nextByWorkspace[workspaceId] ?? [];
      for (const session of sessions) {
        delete nextProjectionBySessionId[session.id];
      }
      delete nextByWorkspace[workspaceId];
      delete nextActive[workspaceId];
      delete nextLoading[workspaceId];
      return {
        byWorkspace: nextByWorkspace,
        activeComputeSessionIdByWorkspace: nextActive,
        isLoadingByWorkspace: nextLoading,
        projectionBySessionId: nextProjectionBySessionId,
      };
    });
  },
}));

