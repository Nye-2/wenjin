import { useEffect } from "react";

import { subscribeWorkspaceEvents } from "@/lib/api/streams";
import { useWorkflowStore } from "@/stores/workflow-store";

export function useWorkflowSubscription(workspaceId: string): void {
  useEffect(() => {
    const unsubscribe = subscribeWorkspaceEvents(workspaceId, (event) => {
      if (event.type === "subagent.updated") {
        useWorkflowStore.getState().upsertSubagentEvent(event);
      }
    });

    return unsubscribe;
  }, [workspaceId]);
}
