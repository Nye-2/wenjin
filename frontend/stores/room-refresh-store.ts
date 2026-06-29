import { create } from "zustand";

export type RoomRefreshTarget =
  | "library"
  | "decisions"
  | "tasks"
  | "settings"
  | "runs"
  | "prism";

type RoomRefreshCounters = Partial<Record<RoomRefreshTarget, number>>;

interface RoomRefreshState {
  countersByWorkspace: Record<string, RoomRefreshCounters>;
  bump: (workspaceId: string, targets: string[]) => void;
  getCounter: (workspaceId: string, target: RoomRefreshTarget) => number;
  reset: () => void;
}

const ROOM_REFRESH_TARGETS = new Set<RoomRefreshTarget>([
  "library",
  "decisions",
  "tasks",
  "settings",
  "runs",
  "prism",
]);

function normalizeRoomTarget(target: string): RoomRefreshTarget | null {
  if (target === "references") {
    return "library";
  }
  return ROOM_REFRESH_TARGETS.has(target as RoomRefreshTarget)
    ? (target as RoomRefreshTarget)
    : null;
}

export const useRoomRefreshStore = create<RoomRefreshState>((set, get) => ({
  countersByWorkspace: {},

  bump: (workspaceId: string, targets: string[]) => {
    const normalizedTargets = targets
      .map(normalizeRoomTarget)
      .filter((target): target is RoomRefreshTarget => target !== null);
    if (normalizedTargets.length === 0) {
      return;
    }

    set((state) => {
      const current = state.countersByWorkspace[workspaceId] ?? {};
      const next = { ...current };
      for (const target of normalizedTargets) {
        next[target] = (next[target] ?? 0) + 1;
      }
      return {
        countersByWorkspace: {
          ...state.countersByWorkspace,
          [workspaceId]: next,
        },
      };
    });
  },

  getCounter: (workspaceId: string, target: RoomRefreshTarget) =>
    get().countersByWorkspace[workspaceId]?.[target] ?? 0,

  reset: () => {
    set({ countersByWorkspace: {} });
  },
}));
