/**
 * useChatStream — React hook for SSE streaming workspace events into chat store
 * and bridging execution events into the execution store.
 */

import { useEffect } from "react";

import { subscribeWorkspaceEvents } from "@/lib/api";
import { getExecution } from "@/lib/api/executions";
import { useChatStoreV2 } from "@/stores/chat-store";
import { useExecutionStore } from "@/stores/execution-store";

export function useChatStream(workspaceId: string) {
  const handleEvent = useChatStoreV2((s) => s.handleEvent);

  useEffect(() => {
    if (!workspaceId) return;

    const disconnect = subscribeWorkspaceEvents(workspaceId, (event) => {
      const etype = event.type as string;

      // Forward chat-relevant events
      if (etype?.startsWith("chat.")) {
        handleEvent(event as never);
      }

      // Bridge execution events into the execution store
      if (
        etype === "execution.updated" ||
        etype === "execution.completed" ||
        etype === "execution.failed"
      ) {
        const eid = (event as { execution_id?: string }).execution_id;
        if (!eid) return;

        const execStore = useExecutionStore.getState();
        execStore.setCurrentExecution(eid);

        // Fetch full record so graph renders immediately
        getExecution(eid)
          .then((record) => {
            execStore.upsertExecution(record);

            // Bridge completed execution into chat store as result_card
            if (record.result?.task_report) {
              const tr = record.result.task_report as Record<string, unknown>;
              handleEvent({
                type: "execution.completed" as const,
                data: {
                  execution_id: (tr.execution_id as string) ?? eid,
                  capability_name: tr.capability_id as string | undefined,
                  status: (tr.status as "completed" | "failed_partial" | "cancelled") ?? "completed",
                  outputs: ((tr.outputs as Record<string, unknown>[]) ?? []).map(
                    (o) => ({
                      id: o.id as string,
                      kind: o.kind as string,
                      preview: o.preview as string,
                      default_checked: o.default_checked as boolean,
                      data: o.data as Record<string, unknown>,
                    }),
                  ),
                  narrative: tr.narrative as string | undefined,
                  duration_seconds: tr.duration_seconds as number | undefined,
                  errors: ((tr.errors as Record<string, unknown>[]) ?? []).map(
                    (e) => ({
                      message: e.error as string,
                      phase: e.phase as string | undefined,
                      task: e.task as string | undefined,
                    }),
                  ),
                },
              });
            }
          })
          .catch((err) => {
            console.error("[useChatStream] Failed to fetch execution record:", err);
          });

        const status = (event as { status?: string }).status;
        if (
          status === "completed" ||
          status === "failed_partial" ||
          status === "failed" ||
          status === "cancelled"
        ) {
          setTimeout(() => {
            if (useExecutionStore.getState().currentExecutionId === eid) {
              execStore.setCurrentExecution(null);
            }
          }, 5000);
        }
      }
    });

    return disconnect;
  }, [workspaceId, handleEvent]);
}
