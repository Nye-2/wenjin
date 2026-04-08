"use client";

import { useEffect } from "react";
import { subscribeWorkspaceEvents, type WorkspaceEvent } from "@/lib/api";
import { useChatStore } from "@/stores/chat";
import { useDashboardStore } from "@/stores/dashboard";
import { useFeaturePanelStore } from "@/stores/panels";
import { useFeaturesStore } from "@/stores/features";
import { useTaskStore } from "@/stores/task";
import { useWorkspaceStore } from "@/stores/workspace";

function normalizePreview(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized ? normalized : null;
}

function activeThreadNeedsReload(
  chatStore: ReturnType<typeof useChatStore.getState>,
  event: Extract<WorkspaceEvent, { type: "thread.updated" }>
): boolean {
  if (chatStore.threadId !== event.thread.id || chatStore.isStreaming) {
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

function refreshWorkspaceTargets(workspaceId: string, targets: string[]) {
  const workspaceStore = useWorkspaceStore.getState();
  const chatStore = useChatStore.getState();
  const dashboardStore = useDashboardStore.getState();

  const targetSet = new Set(targets);
  if (targetSet.has("activity")) {
    void workspaceStore.fetchActivity(workspaceId);
  }
  if (targetSet.has("artifacts")) {
    void workspaceStore.fetchArtifacts(workspaceId);
  }
  if (targetSet.has("papers")) {
    void workspaceStore.fetchPapers(workspaceId);
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

function handleWorkspaceEvent(workspaceId: string, event: WorkspaceEvent) {
  const taskStore = useTaskStore.getState();
  const chatStore = useChatStore.getState();
  const featurePanelStore = useFeaturePanelStore.getState();
  const workspaceStore = useWorkspaceStore.getState();
  const featureStore = useFeaturesStore.getState();
  const resolveFeature = (featureId: string) => featureStore.getFeatureById(featureId);

  switch (event.type) {
    case "task.updated": {
      featurePanelStore.upsertTaskSession(
        workspaceId,
        event.task,
        resolveFeature
      );
      if (event.activity) {
        workspaceStore.upsertActivity(event.activity);
      }
      if (event.task.task_type === "paper_extraction") {
        chatStore.syncAttachmentExtractionTask(event.task);
      }
      if (event.task.status === "running" || event.task.status === "pending") {
        taskStore.syncTaskProgress({
          workspaceId,
          taskId: event.task.task_id,
          progress: event.task.progress,
          thinking: event.task.message ?? undefined,
        });
      } else if (event.task.status === "success") {
        taskStore.completeTask({
          workspaceId,
          taskId: event.task.task_id,
        });
      } else if (event.task.status === "failed") {
        taskStore.failTask({
          workspaceId,
          taskId: event.task.task_id,
          error: event.task.error || event.task.message || "Task failed",
        });
      } else if (event.task.status === "cancelled") {
        taskStore.cancelTask({
          workspaceId,
          taskId: event.task.task_id,
        });
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
        void chatStore.refreshCurrentThread(workspaceId, {
          preservePendingSkill: true,
        });
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
    case "subagent.updated":
      featurePanelStore.appendSubagentUpdate(workspaceId, event);
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
  useEffect(() => {
    if (!workspaceId) {
      return;
    }

    let disposed = false;
    let disconnect = () => {};
    let reconnectTimer: number | null = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 10;
    const BASE_DELAY = 1500;

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
          handleWorkspaceEvent(workspaceId, event);
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
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
    };
  }, [workspaceId]);
}
