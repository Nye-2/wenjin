"use client";

import { useEffect, useRef } from "react";
import { subscribeExecutionStream } from "@/lib/api/executions";
import type { ExecutionStreamEvent } from "@/lib/api/types";
import { useExecutionStore } from "@/stores/execution-store";

/**
 * Subscribe to a single execution's SSE stream and feed events into the
 * execution store.
 */
export function useExecutionStream(executionId: string | null) {
  const applyEvent = useExecutionStore((s) => s.applyStreamEvent);
  const disconnectRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!executionId) {
      return;
    }

    let disposed = false;

    const disconnect = subscribeExecutionStream(
      executionId,
      (event: ExecutionStreamEvent) => {
        if (disposed) return;
        applyEvent(event);
      },
      (error) => {
        if (disposed) return;
        console.warn("Execution stream error:", error);
      },
      () => {
        if (disposed) return;
        // Stream ended naturally — no-op, the store already has terminal state
      }
    );

    disconnectRef.current = disconnect;

    return () => {
      disposed = true;
      disconnect();
      disconnectRef.current = null;
    };
  }, [executionId, applyEvent]);

  return {
    disconnect: () => {
      disconnectRef.current?.();
    },
  };
}
