"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  getMissionView,
  listWorkspaceMissions,
  subscribeMissionEvents,
} from "@/lib/api/missions";
import type { MissionView } from "@/lib/api/mission-types";

export function useMissionWorkspace(
  workspaceId: string,
  focusedMissionId: string | null,
) {
  const [view, setView] = useState<MissionView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const viewRef = useRef<MissionView | null>(null);
  const focusedMissionIdRef = useRef(focusedMissionId);
  const refreshTokenRef = useRef(0);

  const commitView = useCallback((next: MissionView | null) => {
    viewRef.current = next;
    setView(next);
  }, []);

  useEffect(() => {
    focusedMissionIdRef.current = focusedMissionId;
  }, [focusedMissionId]);

  const refresh = useCallback(
    async (missionId?: string | null) => {
      const token = ++refreshTokenRef.current;
      try {
        const targetId =
          missionId ??
          viewRef.current?.missionId ??
          (await listWorkspaceMissions(workspaceId))[0]?.missionId ??
          null;
        if (!targetId) {
          if (token === refreshTokenRef.current) commitView(null);
          return null;
        }
        const next = await getMissionView(targetId);
        if (token === refreshTokenRef.current) {
          commitView(next);
          setError(null);
        }
        return next;
      } catch (reason) {
        if (token === refreshTokenRef.current) {
          setError(reason instanceof Error ? reason.message : "研究任务加载失败");
        }
        return null;
      } finally {
        if (token === refreshTokenRef.current) setLoading(false);
      }
    },
    [commitView, workspaceId],
  );

  useEffect(() => {
    commitView(null);
    setLoading(true);
    setError(null);
    void refresh(null);
  }, [commitView, refresh, workspaceId]);

  useEffect(() => {
    let refreshTimer: ReturnType<typeof setTimeout> | null = null;
    const scheduleRefresh = (missionId?: string) => {
      if (refreshTimer) clearTimeout(refreshTimer);
      refreshTimer = setTimeout(() => void refresh(missionId), 80);
    };
    const unsubscribe = subscribeMissionEvents({
      workspaceId,
      onEvent(event) {
        const current = viewRef.current;
        const attachedMissionId = focusedMissionIdRef.current;
        const visibleMissionId = attachedMissionId ?? current?.missionId ?? null;
        if (visibleMissionId && event.missionId !== visibleMissionId) {
          return;
        }
        const gap = event.replayRequired || Boolean(current && event.lastItemSeq > current.lastItemSeq + 1);
        const rollback = current && event.stateVersion < current.stateVersion;
        if (gap || rollback || !current) {
          scheduleRefresh(visibleMissionId ?? event.missionId);
          return;
        }
        // Events are invalidation hints. Even contiguous events are refreshed
        // from MissionView instead of being reduced into lifecycle truth here.
        scheduleRefresh(visibleMissionId ?? undefined);
      },
      onReconnect() {
        scheduleRefresh(focusedMissionIdRef.current ?? viewRef.current?.missionId);
      },
    });
    return () => {
      unsubscribe();
      if (refreshTimer) clearTimeout(refreshTimer);
    };
  }, [refresh, workspaceId]);

  return { view, loading, error, refresh, setView: commitView };
}
