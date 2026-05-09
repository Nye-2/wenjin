"use client";

import { useEffect, useRef, useState } from "react";
import { subscribeWorkspaceEvents, type WorkspaceEvent } from "@/lib/api";
import { useDashboardStore } from "@/stores/dashboard";
import { useComputeStore } from "@/stores/compute";
import { useWorkspaceStore } from "@/stores/workspace";
import { useExecutionStream } from "@/hooks/useExecutionStream";

function normalizePreview(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized ? normalized : null;
}

function refreshWorkspaceTargets(workspaceId: string, targets: string[]) {
  const workspaceStore = useWorkspaceStore.getState();
  const dashboardStore = useDashboardStore.getState();

  const targetSet = new Set(targets);
  if (targetSet.has("activity")) {
    void workspaceStore.fetchActivity(workspaceId);
  }
  if (targetSet.has("artifacts")) {
    void workspaceStore.fetchArtifacts(workspaceId);
  }
  if (targetSet.has("references")) {
    void workspaceStore.fetchReferences(workspaceId);
  }
  if (targetSet.has("workspace")) {
    void workspaceStore.loadWorkspace(workspaceId);
  }
  if (targetSet.has("dashboard")) {
    void dashboardStore.fetchDashboard(workspaceId);
  }
}

function handleWorkspaceEvent(
  workspaceId: string,
  event: WorkspaceEvent,
  options?: {
    scheduleComputeHydrate?: () => void;
  }
) {
  const computeStore = useComputeStore.getState();
  const workspaceStore = useWorkspaceStore.getState();

  switch (event.type) {
    case "task.updated": {
      if (event.activity) {
        workspaceStore.upsertActivity(event.activity);
      }
      break;
    }
    case "thread.status":
    case "thread.updated":
    case "thread.deleted":
      // v2 chat is managed by its own SSE stream; ignore thread events here
      if (event.type === "thread.updated" || event.type === "thread.deleted") {
        if ("activity" in event && event.activity) {
          workspaceStore.upsertActivity(event.activity);
        } else {
          refreshWorkspaceTargets(workspaceId, ["activity"]);
        }
      }
      break;
    case "compute.created":
    case "compute.updated":
      computeStore.upsertComputeSession(workspaceId, event.compute_session);
      void computeStore.fetchProjection(event.compute_session.id);
      break;
    case "subagent.updated":
      if (event.activity) {
        workspaceStore.upsertActivity(event.activity);
      } else {
        refreshWorkspaceTargets(workspaceId, ["activity"]);
      }
      break;
    case "workspace.refresh":
      refreshWorkspaceTargets(workspaceId, event.refresh_targets || []);
      break;
    case "execution.updated":
    case "execution.completed":
    case "execution.failed": {
      // Phase 6: Unified execution notifications — route to execution store
      // via the execution stream subscriber managed by useWorkspaceEventStream.
      break;
    }
    case "workspace.ready":
      break;
    default:
      break;
  }
}

export function useWorkspaceEventStream(workspaceId: string | null) {
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);

  // Subscribe to the unified execution stream when an execution is active.
  useExecutionStream(activeExecutionId);

  const inFlightComputeHydrateRef = useRef(false);

  useEffect(() => {
    if (!workspaceId) {
      return;
    }

    inFlightComputeHydrateRef.current = false;

    let disposed = false;
    let disconnect = () => {};
    let reconnectTimer: number | null = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 10;
    const BASE_DELAY = 1500;

    const scheduleComputeHydrate = () => {
      if (inFlightComputeHydrateRef.current) {
        return;
      }
      const computeState = useComputeStore.getState();
      if (computeState.isLoadingByWorkspace[workspaceId]) {
        return;
      }
      inFlightComputeHydrateRef.current = true;
      void computeState.hydrateWorkspace(workspaceId).finally(() => {
        inFlightComputeHydrateRef.current = false;
      });
    };

    const connect = () => {
      disconnect();
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      disconnect = subscribeWorkspaceEvents(
        workspaceId,
        (event) => {
          reconnectAttempts = 0;

          // Phase 6: When a unified execution notification arrives, start
          // (or stop) the execution stream subscription.
          if (
            event.type === "execution.updated" ||
            event.type === "execution.completed" ||
            event.type === "execution.failed"
          ) {
            if (event.execution_id) {
              if (event.status === "running") {
                setActiveExecutionId(event.execution_id);
              } else if (
                event.event_type === "execution.completed" ||
                event.event_type === "execution.error"
              ) {
                // Terminal — give the stream a few seconds to drain
                window.setTimeout(() => setActiveExecutionId(null), 3000);
              }
            }
          }

          handleWorkspaceEvent(workspaceId, event, {
            scheduleComputeHydrate,
          });
        },
        () => {
          if (disposed) {
            return;
          }
          // Keep reconnecting indefinitely with bounded exponential backoff.
          // 1.5s, 3s, 6s, ... then capped at the MAX_RECONNECT_ATTEMPTS tier.
          const boundedAttempts = Math.min(
            reconnectAttempts,
            MAX_RECONNECT_ATTEMPTS
          );
          const delay = Math.min(
            BASE_DELAY * Math.pow(2, boundedAttempts) + Math.random() * 500,
            60000,
          );
          reconnectAttempts = boundedAttempts + 1;
          reconnectTimer = window.setTimeout(() => {
            connect();
          }, delay);
        },
        () => {
          reconnectAttempts = 0;
        }
      );
    };

    connect();

    return () => {
      disposed = true;
      disconnect();
      inFlightComputeHydrateRef.current = false;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
    };
  }, [workspaceId]);
}
