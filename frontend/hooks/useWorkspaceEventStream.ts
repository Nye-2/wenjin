"use client";

import { useEffect, useRef } from "react";

import { isTerminalEventStreamStatus } from "@/lib/api/client";
import { subscribeWorkspaceEvents, type WorkspaceEvent } from "@/lib/api";
import { useDashboardStore } from "@/stores/dashboard";
import { useChatStoreV2 } from "@/stores/chat-store";
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
  if (event.type === "workspace.refresh") {
    refreshWorkspaceTargets(workspaceId, event.refresh_targets ?? []);
  }
  if (event.type === "thread.updated") {
    const chat = useChatStoreV2.getState();
    if (
      chat.getThreadId(workspaceId) === event.thread.id &&
      chat.activeRequestWorkspaceId !== workspaceId
    ) {
      void chat.refreshHistory(workspaceId);
    }
  }
  // Mission events have their own hint stream. They are intentionally not
  // reduced here because MissionView is the only lifecycle projection.
}

function reconcileChatAfterWorkspaceReconnect(workspaceId: string) {
  const chat = useChatStoreV2.getState();
  const threadId = chat.getThreadId(workspaceId);
  if (!threadId || chat.activeRequestWorkspaceId === workspaceId) return;
  void chat.refreshHistory(workspaceId).then((refreshedThreadId) => {
    if (!refreshedThreadId) return;
    void useChatStoreV2
      .getState()
      .recoverActiveRun(workspaceId, refreshedThreadId);
  });
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
        (_message, status) => {
          if (closed) return;
          if (isTerminalEventStreamStatus(status)) {
            closed = true;
            unsubscribe?.();
            return;
          }
          reconnectTimerRef.current = setTimeout(connect, 1200);
        },
        () => reconcileChatAfterWorkspaceReconnect(workspaceId),
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
