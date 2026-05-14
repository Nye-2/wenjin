"use client";

import { useEffect, useRef, useState } from "react";
import { subscribeWorkspaceEvents, type WorkspaceEvent } from "@/lib/api";
import { getExecution } from "@/lib/api/executions";
import { useDashboardStore } from "@/stores/dashboard";
import { useComputeStore } from "@/stores/compute";
import { useChatStoreV2 } from "@/stores/chat-store";
import type { ResultCardData } from "@/stores/chat-store";
import { useWorkspaceStore } from "@/stores/workspace";
import { useExecutionStore } from "@/stores/execution-store";
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

function isExecutionNotification(event: WorkspaceEvent): event is Extract<
  WorkspaceEvent,
  { type: "execution.updated" | "execution.completed" | "execution.failed" }
> {
  return (
    event.type === "execution.updated" ||
    event.type === "execution.completed" ||
    event.type === "execution.failed"
  );
}

function isTerminalExecutionStatus(status: string | null | undefined): boolean {
  return (
    status === "completed" ||
    status === "failed_partial" ||
    status === "failed" ||
    status === "cancelled"
  );
}

function resultCardFromTaskReport(
  executionId: string,
  taskReport: Record<string, unknown>,
): ResultCardData {
  return {
    execution_id: (taskReport.execution_id as string) || executionId,
    capability_name: taskReport.capability_id as string | undefined,
    status:
      (taskReport.status as ResultCardData["status"] | undefined) || "completed",
    outputs: ((taskReport.outputs as Record<string, unknown>[] | undefined) ?? []).map(
      (output) => ({
        id: output.id as string,
        kind: output.kind as string,
        preview: output.preview as string,
        default_checked: output.default_checked as boolean,
        data: output.data as Record<string, unknown>,
      }),
    ),
    narrative: taskReport.narrative as string | undefined,
    duration_seconds: taskReport.duration_seconds as number | undefined,
    errors: ((taskReport.errors as Record<string, unknown>[] | undefined) ?? []).map(
      (error) => ({
        message: error.error as string,
        phase: error.phase as string | undefined,
        task: error.task as string | undefined,
      }),
    ),
  };
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
  const deliveredResultCardsRef = useRef<Set<string>>(new Set());

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

          // This hook is the single owner of execution stream subscriptions.
          if (isExecutionNotification(event)) {
            if (event.execution_id) {
              const execStore = useExecutionStore.getState();
              execStore.setCurrentExecution(event.execution_id);

              void getExecution(event.execution_id)
                .then((record) => {
                  execStore.upsertExecution(record);

                  const taskReport = record.result?.task_report;
                  const shouldDeliverResultCard =
                    isTerminalExecutionStatus(record.status) &&
                    taskReport &&
                    typeof taskReport === "object" &&
                    !Array.isArray(taskReport) &&
                    !deliveredResultCardsRef.current.has(record.id);
                  if (shouldDeliverResultCard) {
                    useChatStoreV2.getState().handleEvent({
                      type: "execution.completed",
                      data: resultCardFromTaskReport(
                        record.id,
                        taskReport as Record<string, unknown>,
                      ),
                    });
                    deliveredResultCardsRef.current.add(record.id);
                  }
                })
                .catch((err) => {
                  console.error("[useWorkspaceEventStream] Failed to fetch execution record:", err);
                });

              if (!isTerminalExecutionStatus(event.status)) {
                setActiveExecutionId(event.execution_id);
              } else {
                window.setTimeout(() => setActiveExecutionId(null), 3000);
              }
            }
          }

          handleWorkspaceEvent(workspaceId, event, {
            scheduleComputeHydrate,
          });
        },
        (_message, status) => {
          if (disposed) {
            return;
          }
          // Terminal HTTP errors (workspace gone / not authorized) — stop the
          // retry loop. Without this, a stale tab pointing at a non-existent
          // workspace id (e.g. ``/workspaces/v2``) hammers the gateway
          // indefinitely and exhausts the per-IP rate-limit bucket for the
          // whole tab.
          if (status === 404 || status === 403 || status === 410) {
            disposed = true;
            return;
          }
          // Keep reconnecting otherwise with bounded exponential backoff.
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
      setActiveExecutionId(null);
      inFlightComputeHydrateRef.current = false;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
    };
  }, [workspaceId]);
}
