import {
  API_BASE_URL,
  authorizedFetch,
  readErrorMessage,
  subscribeJsonEventStream,
} from "@/lib/api/client";
import type {
  ChatMessage,
  ChatRequest,
  TaskProgressEvent,
  WorkspaceEvent,
} from "@/lib/api/types";

export function streamChat(
  data: ChatRequest,
  onMessage: (content: string) => void,
  onReasoning?: (content: string) => void,
  onThreadId?: (context: { threadId: string; skill: string | null }) => void,
  onAssistantMessage?: (message: ChatMessage) => void,
  onError?: (error: string) => void,
  onDone?: () => void
): () => void {
  const controller = new AbortController();

  authorizedFetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ...data, stream: true }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("No reader available");
      }

      const decoder = new TextDecoder();
      let buffer = "";
      let finished = false;

      const processLine = (line: string) => {
        if (!line.startsWith("data: ")) {
          return;
        }

        const payload = line.slice(6).trim();
        if (!payload) {
          return;
        }

        try {
          const json = JSON.parse(payload);
          switch (json.type) {
            case "thread_id":
              onThreadId?.({
                threadId: json.thread_id,
                skill: typeof json.skill === "string" ? json.skill : null,
              });
              break;
            case "content":
              onMessage(json.content);
              break;
            case "reasoning":
              onReasoning?.(json.content);
              break;
            case "assistant_message":
              onAssistantMessage?.(json.message as ChatMessage);
              break;
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

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const rawLine of lines) {
          processLine(rawLine.trim());
        }
      }

      buffer += decoder.decode();
      const remaining = buffer.trim();
      if (remaining) {
        for (const rawLine of remaining.split("\n")) {
          processLine(rawLine.trim());
        }
      }

      if (!finished) {
        onDone?.();
      }
    })
    .catch((error: unknown) => {
      const errorName =
        error instanceof DOMException
          ? error.name
          : typeof error === "object" && error && "name" in error
            ? String(error.name)
            : "";
      if (errorName !== "AbortError") {
        onError?.(error instanceof Error ? error.message : "Unknown stream error");
      }
    });

  return () => controller.abort();
}

export function subscribeWorkspaceEvents(
  workspaceId: string,
  onEvent: (event: WorkspaceEvent) => void,
  onError?: (error: string) => void,
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

export function subscribeTaskProgress(
  taskId: string,
  onUpdate: (event: TaskProgressEvent) => void,
  onError?: (error: string) => void
): () => void {
  return subscribeJsonEventStream<TaskProgressEvent>({
    url: `${API_BASE_URL}/tasks/${taskId}/stream`,
    init: { method: "GET" },
    onPayload: onUpdate,
    onError,
    onClosedMessage: "Task progress stream closed",
  });
}
