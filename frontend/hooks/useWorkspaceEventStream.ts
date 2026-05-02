"use client";

import { useEffect, useRef } from "react";
import { subscribeWorkspaceEvents, type WorkspaceEvent } from "@/lib/api";
import { useThreadStore } from "@/stores/thread";
import { useDashboardStore } from "@/stores/dashboard";
import { useExecutionStore } from "@/stores/execution";
import { useComputeStore } from "@/stores/compute";
import { useWorkspaceStore } from "@/stores/workspace";

function normalizePreview(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized ? normalized : null;
}

function activeThreadNeedsReload(
  chatStore: ReturnType<typeof useThreadStore.getState>,
  event: Extract<WorkspaceEvent, { type: "thread.updated" }>
): boolean {
  if (
    chatStore.threadId !== event.thread.id ||
    chatStore.isStreaming ||
    chatStore.isThreadLoading ||
    chatStore.isWorkspaceThreadLoading
  ) {
    return false;
  }

  const currentSummary = chatStore.currentThreadSummary;
  if (
    currentSummary?.id === event.thread.id &&
    currentSummary.updated_at === event.thread.updated_at
  ) {
    return false;
  }

  const summaryMessageCount = event.thread.message_count;
  if (
    typeof summaryMessageCount === "number" &&
    summaryMessageCount !== chatStore.messages.length
  ) {
    return true;
  }

  const localLastMessage = chatStore.messages[chatStore.messages.length - 1];
  const localPreview = normalizePreview(localLastMessage?.content);
  const summaryPreview = normalizePreview(event.thread.last_message_preview);

  if ((localLastMessage?.role ?? null) !== (event.thread.last_message_role ?? null)) {
    return true;
  }

  if (localPreview !== summaryPreview) {
    return true;
  }

  const summarySkill = event.thread.skill ?? null;
  if (
    !chatStore.isSkillSelectionPending &&
    (chatStore.threadSkill ?? null) !== summarySkill
  ) {
    return true;
  }

  return false;
}

function buildThreadUpdateVersionKey(
  event: Extract<WorkspaceEvent, { type: "thread.updated" }>
): string {
  return [
    event.thread.id,
    event.thread.updated_at,
    event.thread.message_count ?? "",
    event.thread.last_message_role ?? "",
    normalizePreview(event.thread.last_message_preview) ?? "",
    event.thread.skill ?? "",
  ].join("|");
}

function refreshWorkspaceTargets(workspaceId: string, targets: string[]) {
  const workspaceStore = useWorkspaceStore.getState();
  const chatStore = useThreadStore.getState();
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
  if (targetSet.has("threads")) {
    void chatStore.refreshCurrentThread(workspaceId);
  }
}

function handleWorkspaceEvent(
  workspaceId: string,
  event: WorkspaceEvent,
  options?: {
    scheduleThreadRefresh?: (
      event: Extract<WorkspaceEvent, { type: "thread.updated" }>
    ) => void;
    scheduleExecutionHydrate?: () => void;
    scheduleExecutionHydrateDebounced?: () => void;
    scheduleComputeHydrate?: () => void;
  }
) {
  const chatStore = useThreadStore.getState();
  const executionStore = useExecutionStore.getState();
  const computeStore = useComputeStore.getState();
  const workspaceStore = useWorkspaceStore.getState();

  switch (event.type) {
    case "task.updated": {
      const terminalStatuses = new Set(["success", "failed", "cancelled"]);
      if (
        event.task.execution_session_id &&
        terminalStatuses.has(event.task.status)
      ) {
        options?.scheduleExecutionHydrate?.();
      }
      if (event.activity) {
        workspaceStore.upsertActivity(event.activity);
      }
      if (
        event.task.task_type === "document_preprocess" ||
        event.task.task_type === "reference_preprocess"
      ) {
        chatStore.syncAttachmentPreprocessTask(event.task);
      }
      break;
    }
    case "thread.status":
      chatStore.setThreadStatus(event.thread);
      break;
    case "thread.updated":
      chatStore.syncCurrentThreadSummary(event.thread);
      if (event.activity) {
        workspaceStore.upsertActivity(event.activity);
      } else {
        refreshWorkspaceTargets(workspaceId, ["activity"]);
      }
      if (activeThreadNeedsReload(chatStore, event)) {
        options?.scheduleThreadRefresh?.(event);
      }
      break;
    case "thread.deleted":
      if (chatStore.threadId === event.thread_id) {
        chatStore.clearCurrentThread();
        void chatStore.refreshCurrentThread(workspaceId);
      }
      if (event.activity_id) {
        workspaceStore.removeActivity(event.activity_id);
      } else {
        refreshWorkspaceTargets(workspaceId, ["activity"]);
      }
      break;
    case "execution.created":
    case "execution.updated":
    case "execution.completed":
    case "execution.failed":
      executionStore.upsertExecution(workspaceId, event.execution);
      options?.scheduleComputeHydrate?.();
      break;
    case "compute.created":
    case "compute.updated":
      computeStore.upsertComputeSession(workspaceId, event.compute_session);
      void computeStore.fetchProjection(event.compute_session.id);
      break;
    case "subagent.updated":
      options?.scheduleExecutionHydrateDebounced?.();
      if (event.activity) {
        workspaceStore.upsertActivity(event.activity);
      } else {
        refreshWorkspaceTargets(workspaceId, ["activity"]);
      }
      break;
    case "workspace.refresh":
      refreshWorkspaceTargets(workspaceId, event.refresh_targets || []);
      break;
    case "workspace.ready":
      break;
    default:
      break;
  }
}

export function useWorkspaceEventStream(workspaceId: string | null) {
  const lastThreadRefreshKeyRef = useRef<string | null>(null);
  const inFlightThreadRefreshKeyRef = useRef<string | null>(null);
  const inFlightExecutionHydrateRef = useRef(false);
  const inFlightComputeHydrateRef = useRef(false);
  const executionHydrateDebounceTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!workspaceId) {
      return;
    }

    lastThreadRefreshKeyRef.current = null;
    inFlightThreadRefreshKeyRef.current = null;
    inFlightExecutionHydrateRef.current = false;
    inFlightComputeHydrateRef.current = false;

    let disposed = false;
    let disconnect = () => {};
    let reconnectTimer: number | null = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 10;
    const BASE_DELAY = 1500;

    const scheduleThreadRefresh = (
      event: Extract<WorkspaceEvent, { type: "thread.updated" }>
    ) => {
      const refreshKey = buildThreadUpdateVersionKey(event);
      if (
        inFlightThreadRefreshKeyRef.current === refreshKey ||
        lastThreadRefreshKeyRef.current === refreshKey
      ) {
        return;
      }

      inFlightThreadRefreshKeyRef.current = refreshKey;
      void useThreadStore
        .getState()
        .refreshCurrentThread(workspaceId, {
          preservePendingSkill: true,
        })
        .finally(() => {
          if (inFlightThreadRefreshKeyRef.current === refreshKey) {
            inFlightThreadRefreshKeyRef.current = null;
          }
          lastThreadRefreshKeyRef.current = refreshKey;
        });
    };
    const scheduleExecutionHydrate = () => {
      if (inFlightExecutionHydrateRef.current) {
        return;
      }
      const executionState = useExecutionStore.getState();
      if (executionState.isLoadingByWorkspace[workspaceId]) {
        return;
      }
      inFlightExecutionHydrateRef.current = true;
      void executionState.hydrateWorkspace(workspaceId).finally(() => {
        inFlightExecutionHydrateRef.current = false;
      });
    };
    const scheduleExecutionHydrateDebounced = () => {
      if (executionHydrateDebounceTimerRef.current !== null) {
        window.clearTimeout(executionHydrateDebounceTimerRef.current);
      }
      executionHydrateDebounceTimerRef.current = window.setTimeout(() => {
        executionHydrateDebounceTimerRef.current = null;
        scheduleExecutionHydrate();
      }, 2000);
    };
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
          handleWorkspaceEvent(workspaceId, event, {
            scheduleThreadRefresh,
            scheduleExecutionHydrate,
            scheduleExecutionHydrateDebounced,
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
      inFlightThreadRefreshKeyRef.current = null;
      inFlightExecutionHydrateRef.current = false;
      inFlightComputeHydrateRef.current = false;
      if (executionHydrateDebounceTimerRef.current !== null) {
        window.clearTimeout(executionHydrateDebounceTimerRef.current);
        executionHydrateDebounceTimerRef.current = null;
      }
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
    };
  }, [workspaceId]);
}
