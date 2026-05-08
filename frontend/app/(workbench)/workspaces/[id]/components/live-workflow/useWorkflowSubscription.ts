import { useEffect } from "react";

import type { WorkspaceTaskEvent } from "@/lib/api/types";
import { subscribeWorkspaceEvents } from "@/lib/api/streams";
import { useWorkflowStore } from "@/stores/workflow-store";

export function useWorkflowSubscription(workspaceId: string): void {
  useEffect(() => {
    const unsubscribe = subscribeWorkspaceEvents(workspaceId, (event) => {
      const store = useWorkflowStore.getState();
      if (event.type === "subagent.updated") {
        store.upsertSubagentEvent(event);
      } else if (event.type === "task.updated") {
        const task = (event as WorkspaceTaskEvent).task;
        if (task) {
          store.upsertTaskEvent({
            task_id: task.task_id,
            thread_id: task.thread_id ?? null,
            task_type: task.task_type ?? undefined,
            feature_id: task.feature_id ?? null,
            status: task.status,
            error: task.error ?? undefined,
          });
        }
      }
    });

    return unsubscribe;
  }, [workspaceId]);
}
