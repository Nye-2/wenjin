/**
 * useChatStream — React hook for SSE streaming chat events into chat-store-v2.
 *
 * Opens an EventSource connection to the workspace chat stream endpoint and
 * dispatches every parsed event into the Zustand store via `handleEvent`.
 * EventSource handles automatic reconnection per the spec.
 */

import { useEffect, useRef } from "react";

import { useChatStoreV2 } from "@/stores/chat-store-v2";

export function useChatStream(workspaceId: string) {
  const handleEvent = useChatStoreV2((s) => s.handleEvent);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!workspaceId) return;

    const es = new EventSource(
      `/api/workspaces/${workspaceId}/chat/stream`,
    );
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data);
        handleEvent(event);
      } catch {
        // ignore malformed events
      }
    };

    // Auto-reconnect is handled by EventSource spec.
    // On error, EventSource will try to reconnect automatically.
    es.onerror = () => {
      // EventSource handles reconnection; just log for now
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [workspaceId, handleEvent]);

  return esRef;
}
