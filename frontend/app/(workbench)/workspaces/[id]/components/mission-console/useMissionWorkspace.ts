"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  getMissionView,
  listWorkspaceMissions,
  subscribeMissionEvents,
} from "@/lib/api/missions";
import type { MissionView } from "@/lib/api/mission-types";
import { mergeMissionView } from "@/lib/mission-view";

interface SwitchMissionOptions {
  retainOnFailure?: boolean;
  onAccepted?(view: MissionView): void;
}

interface PendingMissionSwitch {
  missionId: string;
  options: SwitchMissionOptions;
}

const MISSION_LOAD_ERROR = "研究任务加载失败";

export function useMissionWorkspace(workspaceId: string) {
  const [view, setView] = useState<MissionView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [switchingMissionId, setSwitchingMissionId] = useState<string | null>(null);
  const [pendingMissionId, setPendingMissionId] = useState<string | null>(null);
  const viewRef = useRef<MissionView | null>(null);
  const workspaceEpochRef = useRef(0);
  const switchTokenRef = useRef(0);
  const refreshTokenRef = useRef(0);
  const switchingMissionIdRef = useRef<string | null>(null);
  const pendingSwitchRef = useRef<PendingMissionSwitch | null>(null);

  const commitView = useCallback((next: MissionView | null) => {
    viewRef.current = next;
    setView(next);
  }, []);

  const markCurrentViewStale = useCallback((message: string) => {
    setError(message);
    const current = viewRef.current;
    if (current) {
      commitView({ ...current, isStale: true, loadError: message });
    }
  }, [commitView]);

  const acceptProjection = useCallback((next: MissionView): MissionView => {
    const current = viewRef.current;
    const merged = current?.missionId === next.missionId
      ? mergeMissionView(current, next)
      : next;
    const accepted = { ...merged, isStale: false, loadError: null };
    commitView(accepted);
    setError(null);
    return accepted;
  }, [commitView]);

  const switchMission = useCallback(async (
    missionId: string,
    options: SwitchMissionOptions = {},
  ): Promise<MissionView | null> => {
    const normalizedMissionId = missionId.trim();
    if (!normalizedMissionId) return null;

    const workspaceEpoch = workspaceEpochRef.current;
    const token = ++switchTokenRef.current;
    ++refreshTokenRef.current;
    const pendingSwitch = { missionId: normalizedMissionId, options };
    pendingSwitchRef.current = pendingSwitch;
    switchingMissionIdRef.current = normalizedMissionId;
    setSwitchingMissionId(normalizedMissionId);
    setPendingMissionId(null);
    setError(null);
    if (!viewRef.current) setLoading(true);

    try {
      const next = await getMissionView(normalizedMissionId);
      if (
        workspaceEpoch !== workspaceEpochRef.current ||
        token !== switchTokenRef.current
      ) {
        return null;
      }
      if (next.workspaceId !== workspaceId || next.missionId !== normalizedMissionId) {
        throw new Error(MISSION_LOAD_ERROR);
      }

      pendingSwitchRef.current = null;
      switchingMissionIdRef.current = null;
      setPendingMissionId(null);
      setSwitchingMissionId(null);
      setLoading(false);
      const accepted = acceptProjection(next);
      options.onAccepted?.(accepted);
      return accepted;
    } catch (reason) {
      if (
        workspaceEpoch === workspaceEpochRef.current &&
        token === switchTokenRef.current
      ) {
        const message = reason instanceof Error ? reason.message : MISSION_LOAD_ERROR;
        setError(message);
        setLoading(false);
        switchingMissionIdRef.current = null;
        setSwitchingMissionId(null);
        if (options.retainOnFailure) {
          pendingSwitchRef.current = pendingSwitch;
          setPendingMissionId(normalizedMissionId);
        } else {
          pendingSwitchRef.current = null;
          setPendingMissionId(null);
        }
      }
      return null;
    }
  }, [acceptProjection, workspaceId]);

  const refresh = useCallback(async (
    missionId?: string | null,
  ): Promise<MissionView | null> => {
    const current = viewRef.current;
    const targetMissionId = missionId ?? current?.missionId ?? null;
    if (!current || !targetMissionId || targetMissionId !== current.missionId) {
      return null;
    }

    const workspaceEpoch = workspaceEpochRef.current;
    const token = ++refreshTokenRef.current;
    try {
      const next = await getMissionView(targetMissionId);
      if (
        workspaceEpoch !== workspaceEpochRef.current ||
        token !== refreshTokenRef.current ||
        viewRef.current?.missionId !== targetMissionId
      ) {
        return null;
      }
      if (next.workspaceId !== workspaceId || next.missionId !== targetMissionId) {
        throw new Error(MISSION_LOAD_ERROR);
      }
      return acceptProjection(next);
    } catch (reason) {
      if (
        workspaceEpoch === workspaceEpochRef.current &&
        token === refreshTokenRef.current &&
        viewRef.current?.missionId === targetMissionId
      ) {
        markCurrentViewStale(
          reason instanceof Error ? reason.message : MISSION_LOAD_ERROR,
        );
      }
      return null;
    } finally {
      if (workspaceEpoch === workspaceEpochRef.current) setLoading(false);
    }
  }, [acceptProjection, markCurrentViewStale, workspaceId]);

  useEffect(() => {
    const workspaceEpoch = ++workspaceEpochRef.current;
    ++switchTokenRef.current;
    ++refreshTokenRef.current;
    pendingSwitchRef.current = null;
    switchingMissionIdRef.current = null;
    commitView(null);
    setLoading(true);
    setError(null);
    setSwitchingMissionId(null);
    setPendingMissionId(null);
    const initialSwitchToken = switchTokenRef.current;

    void (async () => {
      try {
        const missionId = (await listWorkspaceMissions(workspaceId))[0]?.missionId ?? null;
        if (
          workspaceEpoch !== workspaceEpochRef.current ||
          initialSwitchToken !== switchTokenRef.current
        ) {
          return;
        }
        if (!missionId) {
          setLoading(false);
          return;
        }
        await switchMission(missionId);
      } catch (reason) {
        if (
          workspaceEpoch === workspaceEpochRef.current &&
          initialSwitchToken === switchTokenRef.current
        ) {
          setError(reason instanceof Error ? reason.message : MISSION_LOAD_ERROR);
          setLoading(false);
        }
      }
    })();

    return () => {
      ++workspaceEpochRef.current;
      ++switchTokenRef.current;
      ++refreshTokenRef.current;
      pendingSwitchRef.current = null;
      switchingMissionIdRef.current = null;
    };
  }, [commitView, switchMission, workspaceId]);

  useEffect(() => {
    let refreshTimer: ReturnType<typeof setTimeout> | null = null;
    let switchTimer: ReturnType<typeof setTimeout> | null = null;

    const scheduleCurrentRefresh = () => {
      if (refreshTimer) clearTimeout(refreshTimer);
      refreshTimer = setTimeout(() => void refresh(), 80);
    };
    const schedulePendingSwitch = () => {
      const pending = pendingSwitchRef.current;
      if (!pending || switchingMissionIdRef.current === pending.missionId) return;
      if (switchTimer) clearTimeout(switchTimer);
      switchTimer = setTimeout(() => {
        const latest = pendingSwitchRef.current;
        if (latest) void switchMission(latest.missionId, latest.options);
      }, 80);
    };

    const unsubscribe = subscribeMissionEvents({
      workspaceId,
      onEvent(event) {
        const current = viewRef.current;
        if (current?.missionId === event.missionId) {
          if (
            event.stateVersion <= current.stateVersion &&
            !current.isStale
          ) {
            return;
          }
          scheduleCurrentRefresh();
          return;
        }
        if (pendingSwitchRef.current?.missionId === event.missionId) {
          schedulePendingSwitch();
          return;
        }
        if (!current && !pendingSwitchRef.current) {
          pendingSwitchRef.current = {
            missionId: event.missionId,
            options: { retainOnFailure: true },
          };
          setPendingMissionId(event.missionId);
          schedulePendingSwitch();
        }
      },
      onReconnect() {
        scheduleCurrentRefresh();
        schedulePendingSwitch();
      },
      onError(message) {
        markCurrentViewStale(message);
      },
    });
    return () => {
      unsubscribe();
      if (refreshTimer) clearTimeout(refreshTimer);
      if (switchTimer) clearTimeout(switchTimer);
    };
  }, [markCurrentViewStale, refresh, switchMission, workspaceId]);

  return {
    view,
    loading,
    error,
    switchingMissionId,
    pendingMissionId,
    refresh,
    switchMission,
  };
}
