"use client";

import { useEffect, useRef } from "react";

import { subscribeWorkspaceEvents, type WorkspaceEvent } from "@/lib/api";
import { useDashboardStore } from "@/stores/dashboard";
import { useRoomRefreshStore } from "@/stores/room-refresh-store";
import { useWorkspaceStore } from "@/stores/workspace";

function refreshWorkspaceTargets(workspaceId: string, targets: string[]) {
  const workspace = useWorkspaceStore.getState();
  useRoomRefreshStore.getState().bump(workspaceId, targets);
  if (targets.includes("activity")) void workspace.fetchActivity(workspaceId);
  if (targets.includes("artifacts")) void workspace.fetchArtifacts(workspaceId);
  if (targets.includes("references")) void workspace.fetchReferences(workspaceId);
  if (targets.includes("workspace")) void workspace.loadWorkspace(workspaceId);
  if (targets.includes("dashboard")) {
    void useDashboardStore.getState().fetchDashboard(workspaceId);
  }
}

function handleWorkspaceEvent(workspaceId: string, event: WorkspaceEvent) {
  const workspace = useWorkspaceStore.getState();
  if (event.type === "task.updated" && event.activity) {
    workspace.upsertActivity(event.activity);
    return;
  }
  if (event.type === "thread.updated" || event.type === "thread.deleted") {
    if ("activity" in event && event.activity) workspace.upsertActivity(event.activity);
    else refreshWorkspaceTargets(workspaceId, ["activity"]);
    return;
  }
  if (event.type === "subagent.updated") {
    if (event.activity) workspace.upsertActivity(event.activity);
    else refreshWorkspaceTargets(workspaceId, ["activity"]);
    return;
  }
  if (event.type === "workspace.refresh") {
    refreshWorkspaceTargets(workspaceId, event.refresh_targets ?? []);
  }
  // Mission events have their own hint stream. They are intentionally not
  // reduced here because MissionView is the only lifecycle projection.
}

export function useWorkspaceEventStream(workspaceId: string | null, enabled = true) {
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled || !workspaceId) return;
    let closed = false;
    let unsubscribe: (() => void) | null = null;

    const connect = () => {
      if (closed) return;
      unsubscribe = subscribeWorkspaceEvents(
        workspaceId,
        (event) => handleWorkspaceEvent(workspaceId, event),
        () => {
          if (closed) return;
          reconnectTimerRef.current = setTimeout(connect, 1200);
        },
      );
    };
    connect();

    return () => {
      closed = true;
      unsubscribe?.();
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    };
  }, [enabled, workspaceId]);
}
