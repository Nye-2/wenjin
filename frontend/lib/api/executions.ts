/**
 * API client for unified execution endpoints.
 */

import { API_BASE_URL, authorizedFetch } from "@/lib/api/client";
import type {
  ExecutionRecord,
  ExecutionStreamEvent,
} from "@/lib/api/types";

export async function getExecution(executionId: string): Promise<ExecutionRecord> {
  const response = await authorizedFetch(
    `${API_BASE_URL}/executions/${encodeURIComponent(executionId)}`
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function listExecutions(params?: {
  workspace_id?: string;
  thread_id?: string;
  execution_type?: string;
  status?: string[];
  limit?: number;
}): Promise<{ items: ExecutionRecord[]; count: number }> {
  const query = new URLSearchParams();
  if (params?.workspace_id) query.set("workspace_id", params.workspace_id);
  if (params?.thread_id) query.set("thread_id", params.thread_id);
  if (params?.execution_type) query.set("execution_type", params.execution_type);
  if (params?.status?.length) {
    for (const value of params.status) {
      query.append("status", value);
    }
  }
  if (params?.limit) query.set("limit", String(params.limit));

  const qs = query.toString();
  const response = await authorizedFetch(
    `${API_BASE_URL}/executions${qs ? `?${qs}` : ""}`
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function cancelExecution(
  executionId: string,
  action: "interrupt" | "rollback" = "interrupt"
): Promise<void> {
  const response = await authorizedFetch(
    `${API_BASE_URL}/executions/${encodeURIComponent(executionId)}/cancel?action=${action}`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
}

/**
 * Subscribe to execution stream events via SSE.
 *
 * Supports automatic reconnect with Last-Event-ID resumption.
 * Returns a cleanup function that aborts the stream.
 */
export function subscribeExecutionStream(
  executionId: string,
  onEvent: (event: ExecutionStreamEvent) => void,
  onError?: (error: string) => void,
  onDone?: () => void
): () => void {
  const url = `${API_BASE_URL}/executions/${encodeURIComponent(executionId)}/stream`;
  const MAX_RECONNECT_ATTEMPTS = 3;
  const BASE_RECONNECT_DELAY_MS = 400;

  let disposed = false;
  let finished = false;
  let reconnectAttempts = 0;
  let lastEventId: string | null = null;
  let activeController: AbortController | null = null;

  const processPayload = (payload: string, eventName: string | null) => {
    if (eventName === "end") {
      finished = true;
      onDone?.();
      return;
    }
    if (eventName === "error") {
      try {
        const err = JSON.parse(payload) as { error?: string };
        onError?.(err.error || payload || "Stream error");
      } catch {
        onError?.(payload || "Stream error");
      }
      return;
    }
    if (!payload) return;
    try {
      const json = JSON.parse(payload) as ExecutionStreamEvent;
      onEvent(json);
    } catch {
      // Ignore malformed payloads
    }
  };

  const consumeStream = async (
    response: Response,
    controller: AbortController
  ) => {
    const reader = response.body?.getReader();
    if (!reader) throw new Error("No reader available");

    const decoder = new TextDecoder();
    let buffer = "";
    let frameData: string[] = [];
    let frameEvent: string | null = null;
    let frameId: string | null = null;

    const flushFrame = () => {
      if (!frameData.length) {
        frameEvent = null;
        frameId = null;
        return;
      }
      if (frameId) {
        lastEventId = frameId;
      }
      processPayload(frameData.join("\n"), frameEvent);
      frameData = [];
      frameEvent = null;
      frameId = null;
    };

    const processRawLine = (rawLine: string) => {
      const line = rawLine.replace(/\r$/, "");
      if (!line) {
        flushFrame();
        return;
      }
      if (line.startsWith(":")) return;
      if (line.startsWith("id:")) {
        frameId = line.slice(3).trim() || null;
        return;
      }
      if (line.startsWith("event:")) {
        frameEvent = line.slice(6).trim() || null;
        return;
      }
      if (line.startsWith("data:")) {
        frameData.push(line.slice(5).trimStart());
      }
    };

    while (!controller.signal.aborted) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) processRawLine(line);
    }

    buffer += decoder.decode();
    const trailing = buffer.split("\n");
    for (const line of trailing) processRawLine(line);
    flushFrame();
  };

  const sleep = (ms: number) =>
    new Promise<void>((resolve) => {
      globalThis.setTimeout(resolve, ms);
    });

  const runStream = async () => {
    while (!disposed && !finished) {
      const controller = new AbortController();
      activeController = controller;

      try {
        const response = await authorizedFetch(url, {
          method: "GET",
          signal: controller.signal,
          headers: lastEventId
            ? { "Last-Event-ID": lastEventId }
            : undefined,
        });
        if (!response.ok) {
          throw new Error(await response.text());
        }
        await consumeStream(response, controller);
        reconnectAttempts = 0;
      } catch (error: unknown) {
        if (
          error instanceof DOMException &&
          error.name === "AbortError"
        ) {
          return;
        }

        if (finished || disposed) return;

        reconnectAttempts += 1;
        if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
          onError?.(
            error instanceof Error
              ? error.message
              : String(error)
          );
          return;
        }

        const delay = BASE_RECONNECT_DELAY_MS * reconnectAttempts;
        await sleep(delay);
        if (disposed || finished) return;
        // Retry with Last-Event-ID
        continue;
      }

      // Normal stream end (not aborted)
      if (!disposed && !finished && !controller.signal.aborted) {
        reconnectAttempts += 1;
        if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
          onError?.("Execution stream disconnected");
          return;
        }
        const delay = BASE_RECONNECT_DELAY_MS * reconnectAttempts;
        await sleep(delay);
        if (disposed || finished) return;
        continue;
      }

      break;
    }
  };

  void runStream();

  return () => {
    disposed = true;
    activeController?.abort();
    activeController = null;
  };
}
