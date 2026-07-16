import {
  API_BASE_URL,
  authorizedFetch,
  readErrorMessage,
  subscribeJsonEventStream,
} from "@/lib/api/client";
import type { AgentBlock } from "@/lib/api/blocks";
import type {
  ThreadMessage,
  RunRequest,
  WorkspaceEvent,
} from "@/lib/api/types";

export function resolveThreadStreamUrl(data: RunRequest): string {
  const threadId =
    typeof data.thread_id === "string" ? data.thread_id.trim() : "";
  if (!threadId) {
    throw new Error("thread_id is required for chat turn streaming");
  }
  return `${API_BASE_URL}/threads/${encodeURIComponent(threadId)}/runs/stream`;
}

function toRunStreamUrl(contentLocation: string): string {
  const normalized = contentLocation.trim();
  if (!normalized) {
    return normalized;
  }
  if (normalized.endsWith("/stream")) {
    return normalized;
  }
  return `${normalized.replace(/\/+$/, "")}/stream`;
}

function extractRunIdFromStreamUrl(url: string): string | null {
  const normalized = url.trim();
  if (!normalized) {
    return null;
  }
  const withoutQuery = normalized.split("?")[0]?.split("#")[0] ?? normalized;
  const match = withoutQuery.match(/\/runs\/([^/]+)\/stream\/?$/);
  if (!match || !match[1]) {
    return null;
  }
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

export function streamThread(
  data: RunRequest,
  onMessage: (content: string) => void,
  onReasoning?: (content: string) => void,
  onThreadId?: (threadId: string) => void,
  onAssistantMessage?: (message: ThreadMessage) => void,
  onError?: (error: string) => void,
  onDone?: () => void,
  // Plan 1 T7 — backend now emits per-block events instead of a single
  // `assistant_message`. This callback fires once per block; consumers
  // assemble them into a Message keyed by `messageId`.
  onBlock?: (event: { messageId: string; block: AgentBlock }) => void,
): () => void {
  const controller = new AbortController();
  const requestPayload: RunRequest = {
    on_disconnect: "continue",
    multitask_strategy: "interrupt",
    ...data,
  };
  const requestBody = JSON.stringify(requestPayload);
  const initialUrl = resolveThreadStreamUrl(data);
  const MAX_RECONNECT_ATTEMPTS = 3;
  const BASE_RECONNECT_DELAY_MS = 400;

  let finished = false;
  let failed = false;
  let reconnectAttempts = 0;
  let resumeUrl: string | null = null;
  let lastEventId: string | null = null;
  let activeRunId: string | null = null;

  const processPayload = (payload: string, eventName: string | null) => {
    if (eventName === "end") {
      if (!finished) {
        finished = true;
        onDone?.();
      }
      return;
    }

    if (!payload) {
      return;
    }
    try {
      const json = JSON.parse(payload);
      if (!activeRunId) {
        if (
          eventName === "metadata" &&
          typeof json.run_id === "string" &&
          json.run_id.trim()
        ) {
          activeRunId = json.run_id.trim();
        } else if (
          typeof json.run_id === "string" &&
          json.run_id.trim()
        ) {
          activeRunId = json.run_id.trim();
        }
        if (activeRunId && !resumeUrl) {
          const threadId = requestPayload.thread_id?.trim();
          if (threadId) {
            resumeUrl = `${API_BASE_URL}/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(activeRunId)}/stream`;
          }
        }
      }
      switch (json.type) {
        case "thread_id":
          onThreadId?.(json.thread_id);
          break;
        case "content":
          onMessage(json.content);
          break;
        case "reasoning":
          onReasoning?.(json.content);
          break;
        case "assistant_message":
          onAssistantMessage?.(json.message as ThreadMessage);
          break;
        case "block": {
          // Plan 1 T7 — per-block SSE event. Frontend can assemble blocks
          // into a Message via the shared `messageId`. Until a thread-store
          // consumer exists, this just forwards the payload.
          const messageId =
            typeof json.message_id === "string" ? json.message_id : "";
          const block = json.block as AgentBlock | undefined;
          if (messageId && block) {
            onBlock?.({ messageId, block });
          }
          break;
        }
        case "error":
          onError?.(json.error);
          break;
        case "done":
          if (!finished) {
            finished = true;
            onDone?.();
          }
          break;
      }
    } catch {
      // Ignore malformed SSE payloads.
    }
  };

  const consumeStream = async (response: Response) => {
    const contentLocation = response.headers.get("Content-Location");
    if (contentLocation && contentLocation.trim()) {
      resumeUrl = toRunStreamUrl(contentLocation);
      activeRunId = extractRunIdFromStreamUrl(resumeUrl);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error("No reader available");
    }

    const decoder = new TextDecoder();
    let buffer = "";
    let frameData: string[] = [];
    let frameId: string | null = null;
    let frameEvent: string | null = null;

    const flushFrame = () => {
      if (!frameData.length) {
        frameId = null;
        frameEvent = null;
        return;
      }
      if (frameId) {
        lastEventId = frameId;
      }
      processPayload(frameData.join("\n"), frameEvent);
      frameData = [];
      frameId = null;
      frameEvent = null;
    };

    const processRawLine = (rawLine: string) => {
      const line = rawLine.replace(/\r$/, "");
      if (!line) {
        flushFrame();
        return;
      }
      if (line.startsWith(":")) {
        return;
      }
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
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const rawLine of lines) {
        processRawLine(rawLine);
      }
    }

    buffer += decoder.decode();
    const trailingLines = buffer.split("\n");
    for (const rawLine of trailingLines) {
      processRawLine(rawLine);
    }
    flushFrame();
  };

  const openStream = async (url: string, init: RequestInit): Promise<void> => {
    const response = await authorizedFetch(url, {
      ...init,
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    await consumeStream(response);
  };

  const sleep = (ms: number) =>
    new Promise<void>((resolve) => {
      globalThis.setTimeout(resolve, ms);
    });

  void (async () => {
    let requestUrl = initialUrl;
    let requestInit: RequestInit = {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: requestBody,
    };

    while (!controller.signal.aborted && !finished && !failed) {
      try {
        await openStream(requestUrl, requestInit);
        if (controller.signal.aborted || finished) {
          break;
        }
      } catch (error: unknown) {
        const errorName =
          error instanceof DOMException
            ? error.name
            : typeof error === "object" && error && "name" in error
              ? String(error.name)
              : "";
        if (errorName === "AbortError" || controller.signal.aborted) {
          break;
        }
      }

      if (!resumeUrl || reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        failed = true;
        onError?.("Thread stream disconnected");
        break;
      }

      reconnectAttempts += 1;
      await sleep(BASE_RECONNECT_DELAY_MS * reconnectAttempts);
      if (controller.signal.aborted || finished) {
        break;
      }
      requestUrl = resumeUrl;
      requestInit = {
        method: "GET",
        headers: lastEventId
          ? {
              "Last-Event-ID": lastEventId,
            }
          : undefined,
      };
    }

    if (!finished && !failed && !controller.signal.aborted) {
      onDone?.();
    }
  })();

  return () => {
    if (!controller.signal.aborted && !finished && activeRunId) {
      const threadId = requestPayload.thread_id?.trim();
      if (!threadId) {
        controller.abort();
        return;
      }
      void authorizedFetch(
        `${API_BASE_URL}/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(activeRunId)}/cancel?action=interrupt`,
        { method: "POST", keepalive: true }
      ).catch(() => {
        // Best effort: UI abort should not fail if cancel request errors.
      });
    }
    controller.abort();
  };
}

export function subscribeWorkspaceEvents(
  workspaceId: string,
  onEvent: (event: WorkspaceEvent) => void,
  onError?: (error: string, status?: number) => void,
  onOpen?: () => void
): () => void {
  return subscribeJsonEventStream<WorkspaceEvent>({
    url: `${API_BASE_URL}/workspaces/${workspaceId}/events`,
    init: { method: "GET" },
    onPayload: onEvent,
    onOpen,
    onError,
    onClosedMessage: "Workspace event stream closed",
  });
}
