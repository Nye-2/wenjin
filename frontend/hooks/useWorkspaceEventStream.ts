"use client";

import { useEffect } from "react";
import { subscribeWorkspaceEvents, type WorkspaceEvent } from "@/lib/api";
import { useChatStore } from "@/stores/chat";
import { useDashboardStore } from "@/stores/dashboard";
import { useTaskStore } from "@/stores/task";
import { useWorkspaceStore } from "@/stores/workspace";

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
    void chatStore.loadThreads(workspaceId);
  }
}

function handleWorkspaceEvent(workspaceId: string, event: WorkspaceEvent) {
  const taskStore = useTaskStore.getState();
  const chatStore = useChatStore.getState();
  const workspaceStore = useWorkspaceStore.getState();

  switch (event.type) {
    case "task.updated": {
      if (event.activity) {
        workspaceStore.upsertActivity(event.activity);
      }
      const currentTask = taskStore.currentTask;
      if (currentTask?.id === event.task.task_id) {
        if (event.task.status === "running" || event.task.status === "pending") {
          taskStore.syncTaskProgress(
            event.task.progress,
            event.task.message ?? undefined
          );
        } else if (event.task.status === "success") {
          taskStore.completeTask();
        } else if (event.task.status === "failed") {
          taskStore.failTask(event.task.error || event.task.message || "Task failed");
        } else if (event.task.status === "cancelled") {
          taskStore.cancelTask();
        }
      }
      break;
    }
    case "thread.status":
      chatStore.setThreadStatus(event.thread);
      break;
    case "thread.updated":
      chatStore.upsertThreadSummary(event.thread);
      if (event.activity) {
        workspaceStore.upsertActivity(event.activity);
      } else {
        refreshWorkspaceTargets(workspaceId, ["activity"]);
      }
      if (chatStore.threadId === event.thread.id) {
        void chatStore.loadThread(event.thread.id, {
          preservePendingSkill: true,
        });
      }
      break;
    case "thread.deleted":
      chatStore.removeThread(event.thread_id);
      if (event.activity_id) {
        workspaceStore.removeActivity(event.activity_id);
      } else {
        refreshWorkspaceTargets(workspaceId, ["activity"]);
      }
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

    const connect = () => {
      disconnect = subscribeWorkspaceEvents(
        workspaceId,
        (event) => {
          handleWorkspaceEvent(workspaceId, event);
        },
        () => {
          if (disposed) {
            return;
          }
          reconnectTimer = window.setTimeout(() => {
            connect();
          }, 1500);
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
