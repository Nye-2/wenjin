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

  const markViewStale = useCallback((message: string) => {
    setError(message);
    const current = viewRef.current;
    if (current) {
      commitView({ ...current, isStale: true, loadError: message });
    }
  }, [commitView]);

  const replaceView = useCallback((next: MissionView | null) => {
    commitView(next ? { ...next, isStale: false, loadError: null } : null);
    setError(null);
  }, [commitView]);

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
          replaceView(next);
        }
        return next;
      } catch (reason) {
        if (token === refreshTokenRef.current) {
          markViewStale(reason instanceof Error ? reason.message : "研究任务加载失败");
        }
        return null;
      } finally {
        if (token === refreshTokenRef.current) setLoading(false);
      }
    },
    [commitView, markViewStale, replaceView, workspaceId],
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
        const attachedMissionId = focusedMissionIdRef.current;
        const visibleMissionId = attachedMissionId ?? viewRef.current?.missionId ?? null;
        if (visibleMissionId && event.missionId !== visibleMissionId) {
          return;
        }
        scheduleRefresh(visibleMissionId ?? event.missionId);
      },
      onReconnect() {
        scheduleRefresh(focusedMissionIdRef.current ?? viewRef.current?.missionId);
      },
      onError(message) {
        markViewStale(message);
      },
    });
    return () => {
      unsubscribe();
      if (refreshTimer) clearTimeout(refreshTimer);
    };
  }, [markViewStale, refresh, workspaceId]);

  return { view, loading, error, refresh, setView: replaceView };
}
