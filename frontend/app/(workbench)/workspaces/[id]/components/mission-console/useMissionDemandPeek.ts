"use client";

import { useCallback, useEffect, useRef } from "react";

import type { MissionView } from "@/lib/api/mission-types";
import { missionDemandKey } from "@/lib/mission-view";
import { useMissionUiStore } from "@/stores/mission-ui-store";

type DemandState = {
  workspaceId: string;
  initialized: boolean;
  acknowledgedKey: string | null;
};

export function useMissionDemandPeek({
  workspaceId,
  view,
  loading,
}: {
  workspaceId: string;
  view: MissionView | null;
  loading: boolean;
}) {
  const panelMode = useMissionUiStore((state) => state.panelMode);
  const peekMission = useMissionUiStore((state) => state.peekMission);
  const currentView = view?.workspaceId === workspaceId ? view : null;
  const demandKey = currentView ? missionDemandKey(currentView) : null;
  const demandStateRef = useRef<DemandState>({
    workspaceId,
    initialized: false,
    acknowledgedKey: null,
  });

  useEffect(() => {
    const state = demandStateRef.current;
    if (state.workspaceId !== workspaceId) {
      demandStateRef.current = {
        workspaceId,
        initialized: false,
        acknowledgedKey: null,
      };
    }
  }, [workspaceId]);

  useEffect(() => {
    const state = demandStateRef.current;
    if (state.workspaceId !== workspaceId || loading) return;
    if (!state.initialized) {
      state.initialized = true;
      state.acknowledgedKey = demandKey;
      return;
    }
    if (
      panelMode === "closed" &&
      currentView &&
      demandKey &&
      demandKey !== state.acknowledgedKey
    ) {
      state.acknowledgedKey = demandKey;
      peekMission(currentView.missionId);
    }
  }, [currentView, demandKey, loading, panelMode, peekMission, workspaceId]);

  const acknowledgeCurrentDemand = useCallback(() => {
    demandStateRef.current = {
      workspaceId,
      initialized: true,
      acknowledgedKey: demandKey,
    };
  }, [demandKey, workspaceId]);

  return { demandKey, acknowledgeCurrentDemand };
}
