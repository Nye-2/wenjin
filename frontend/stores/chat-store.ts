/**
 * Chat Store — Zustand store for chat state management.
 * Blocks stored strictly in arrival order.
 */

import { create } from "zustand";
import { authorizedFetch } from "@/lib/api/client";

// ── Data types ──────────────────────────────────────────────────────────────

type QuestionCardData = {
  question: string;
  options?: string[];
  context?: string;
};

export type ResultCardData = {
  execution_id: string;
  capability_name?: string;
  status: "completed" | "failed_partial" | "cancelled";
  outputs: Array<{
    id: string;
    kind: string;
    preview: string;
    default_checked: boolean;
    data: Record<string, unknown>;
  }>;
  narrative?: string;
  duration_seconds?: number;
  errors?: Array<{ message: string; phase?: string; task?: string }>;
};

type ToolInvocationData = {
  tool: string;
  args: Record<string, unknown>;
};

type ToolResultData = {
  execution_id?: string;
  status: string;
  [key: string]: unknown;
};

export type Block =
  | { kind: "text"; content: string }
  | { kind: "thinking"; content: string }
  | { kind: "status_line"; content: string }
  | { kind: "question_card"; data: QuestionCardData }
  | { kind: "result_card"; data: ResultCardData }
  | { kind: "tool_invocation"; data: ToolInvocationData }
  | { kind: "tool_result"; data: ToolResultData };

export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  blocks: Block[];
  createdAt: string;
};

// ── Event type (discriminated union) ────────────────────────────────────────

type ChatEvent =
  | {
      type: "chat.user.message";
      data: {
        id: string;
        content?: string;
        blocks?: Block[];
        timestamp?: string;
        [key: string]: unknown;
      };
    }
  | {
      type: "chat.assistant.start";
      data: { message_id: string; timestamp?: string; [key: string]: unknown };
    }
  | { type: "chat.assistant.thinking"; delta: string }
  | { type: "chat.assistant.block"; block: Block }
  | { type: "chat.assistant.tool_invocation"; data: ToolInvocationData }
  | { type: "chat.assistant.tool_result"; data: ToolResultData }
  | { type: "chat.assistant.completion" }
  | {
      type: "execution.completed";
      data: ResultCardData;
    };

// ── Store interface ─────────────────────────────────────────────────────────

interface ChatState {
  messages: Message[];
  currentAssistantId: string | null;
  isSending: boolean;
  handleEvent(event: ChatEvent): void;
  sendMessage(workspaceId: string, content: string): Promise<void>;
  reset(): void;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Find the index of the current assistant message, or the last assistant message. */
function findAssistantMessageIndex(
  messages: Message[],
  currentAssistantId: string | null,
): number {
  if (currentAssistantId) {
    return messages.findIndex((m) => m.id === currentAssistantId);
  }
  // Fall back to last assistant message
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") return i;
  }
  return -1;
}

// ── Store implementation ────────────────────────────────────────────────────

export const useChatStoreV2 = create<ChatState>((set, get) => ({
  messages: [],
  currentAssistantId: null,
  isSending: false,

  handleEvent(event: ChatEvent) {
    switch (event.type) {
      // ── User message ──────────────────────────────────────────────────
      case "chat.user.message": {
        const blocks: Block[] = event.data.blocks?.length
          ? event.data.blocks
          : [{ kind: "text", content: event.data.content ?? "" }];

        const message: Message = {
          id: event.data.id,
          role: "user",
          blocks,
          createdAt: event.data.timestamp ?? new Date().toISOString(),
        };

        set((state) => ({ messages: [...state.messages, message] }));
        break;
      }

      // ── Assistant start ───────────────────────────────────────────────
      case "chat.assistant.start": {
        const message: Message = {
          id: event.data.message_id,
          role: "assistant",
          blocks: [],
          createdAt: event.data.timestamp ?? new Date().toISOString(),
        };

        set((state) => ({
          messages: [...state.messages, message],
          currentAssistantId: event.data.message_id,
        }));
        break;
      }

      // ── Thinking delta ────────────────────────────────────────────────
      case "chat.assistant.thinking": {
        const { currentAssistantId } = get();
        set((state) => {
          const idx = findAssistantMessageIndex(
            state.messages,
            currentAssistantId,
          );
          if (idx === -1) return state;

          const msg = state.messages[idx];
          const lastBlock = msg.blocks[msg.blocks.length - 1];

          // If last block is thinking, merge the delta into it
          if (lastBlock?.kind === "thinking") {
            const updatedBlocks = [...msg.blocks];
            updatedBlocks[updatedBlocks.length - 1] = {
              ...lastBlock,
              content: lastBlock.content + event.delta,
            };
            const updatedMessages = [...state.messages];
            updatedMessages[idx] = { ...msg, blocks: updatedBlocks };
            return { messages: updatedMessages };
          }

          // Otherwise create a new thinking block — preserves arrival order
          const updatedMessages = [...state.messages];
          updatedMessages[idx] = {
            ...msg,
            blocks: [
              ...msg.blocks,
              { kind: "thinking", content: event.delta },
            ],
          };
          return { messages: updatedMessages };
        });
        break;
      }

      // ── Generic block ─────────────────────────────────────────────────
      case "chat.assistant.block": {
        const { currentAssistantId } = get();
        set((state) => {
          const idx = findAssistantMessageIndex(
            state.messages,
            currentAssistantId,
          );
          if (idx === -1) return state;

          const msg = state.messages[idx];
          const updatedMessages = [...state.messages];
          updatedMessages[idx] = {
            ...msg,
            blocks: [...msg.blocks, event.block],
          };
          return { messages: updatedMessages };
        });
        break;
      }

      // ── Tool invocation ───────────────────────────────────────────────
      case "chat.assistant.tool_invocation": {
        const { currentAssistantId } = get();
        set((state) => {
          const idx = findAssistantMessageIndex(
            state.messages,
            currentAssistantId,
          );
          if (idx === -1) return state;

          const msg = state.messages[idx];
          const updatedMessages = [...state.messages];
          updatedMessages[idx] = {
            ...msg,
            blocks: [
              ...msg.blocks,
              { kind: "tool_invocation", data: event.data },
            ],
          };
          return { messages: updatedMessages };
        });
        break;
      }

      // ── Tool result ───────────────────────────────────────────────────
      case "chat.assistant.tool_result": {
        const { currentAssistantId } = get();
        set((state) => {
          const idx = findAssistantMessageIndex(
            state.messages,
            currentAssistantId,
          );
          if (idx === -1) return state;

          const msg = state.messages[idx];
          const updatedMessages = [...state.messages];
          updatedMessages[idx] = {
            ...msg,
            blocks: [...msg.blocks, { kind: "tool_result", data: event.data }],
          };
          return { messages: updatedMessages };
        });
        break;
      }

      // ── Completion ────────────────────────────────────────────────────
      case "chat.assistant.completion": {
        set({ currentAssistantId: null });
        break;
      }

      // ── Execution completed (async result card) ───────────────────────
      case "execution.completed": {
        const { currentAssistantId } = get();
        set((state) => {
          const idx = findAssistantMessageIndex(
            state.messages,
            currentAssistantId,
          );
          if (idx === -1) return state;

          const msg = state.messages[idx];
          const updatedMessages = [...state.messages];
          updatedMessages[idx] = {
            ...msg,
            blocks: [
              ...msg.blocks,
              { kind: "result_card", data: event.data },
            ],
          };
          return { messages: updatedMessages };
        });
        break;
      }

      default:
        break;
    }
  },

  reset() {
    set({ messages: [], currentAssistantId: null });
  },

  async sendMessage(workspaceId: string, content: string) {
    const { isSending } = get();
    if (isSending || !content.trim()) return;
    set({ isSending: true });

    const userMsgId = crypto.randomUUID();
    get().handleEvent({
      type: "chat.user.message",
      data: { id: userMsgId, content, timestamp: new Date().toISOString() },
    });

    try {
      // Ensure thread exists
      const threadRes = await authorizedFetch(
        `/api/workspaces/${workspaceId}/thread`,
        { method: "POST", headers: { "Content-Type": "application/json" } },
      );
      if (!threadRes.ok) throw new Error("Failed to create thread");
      const thread = await threadRes.json();
      const threadId = thread.id;

      // Create assistant placeholder
      const assistantMsgId = crypto.randomUUID();
      get().handleEvent({
        type: "chat.assistant.start",
        data: { message_id: assistantMsgId },
      });

      // Stream run response — backend expects RunCreateRequest { message, ... }
      const res = await authorizedFetch(
        `/api/threads/${threadId}/runs/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: content, workspace_id: workspaceId }),
        },
      );

      if (!res.ok) throw new Error("Failed to start run");
      if (!res.body) throw new Error("No response body");

      // Parse SSE from fetch response
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let frameData: string[] = [];
      let frameEvent: string | null = null;

      const flushFrame = () => {
        if (!frameData.length) {
          frameEvent = null;
          return;
        }
        const payload = frameData.join("\n");
        frameData = [];
        const eventName = frameEvent;
        frameEvent = null;

        if (eventName === "end") return;
        if (!payload || payload === "null") return;

        try {
          const data = JSON.parse(payload);
          const store = get();

          // Backend run stream events: reasoning, content, block, done, error
          switch (eventName) {
            case "reasoning": {
              store.handleEvent({
                type: "chat.assistant.thinking",
                delta: data.content ?? "",
              });
              break;
            }
            case "content": {
              store.handleEvent({
                type: "chat.assistant.block",
                block: { kind: "text", content: data.content ?? "" },
              });
              break;
            }
            case "block": {
              if (data.block) {
                store.handleEvent({
                  type: "chat.assistant.block",
                  block: data.block as Block,
                });
              }
              break;
            }
            case "error": {
              store.handleEvent({
                type: "chat.assistant.block",
                block: {
                  kind: "status_line",
                  content: data.error ?? "Unknown error",
                },
              });
              break;
            }
            default:
              break;
          }
        } catch {
          // Skip malformed frames
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          const trimmed = line.replace(/\r$/, "");
          if (!trimmed) {
            flushFrame();
            continue;
          }
          if (trimmed.startsWith(":")) continue;
          if (trimmed.startsWith("event:")) {
            frameEvent = trimmed.slice(6).trim() || null;
          } else if (trimmed.startsWith("data:")) {
            frameData.push(trimmed.slice(5).trimStart());
          }
        }
      }
      buffer += decoder.decode();
      for (const line of buffer.split("\n")) {
        const trimmed = line.replace(/\r$/, "");
        if (!trimmed) {
          flushFrame();
          continue;
        }
        if (trimmed.startsWith(":")) continue;
        if (trimmed.startsWith("event:")) {
          frameEvent = trimmed.slice(6).trim() || null;
        } else if (trimmed.startsWith("data:")) {
          frameData.push(trimmed.slice(5).trimStart());
        }
      }
      flushFrame();

      get().handleEvent({ type: "chat.assistant.completion" });
    } catch {
      get().handleEvent({ type: "chat.assistant.completion" });
    } finally {
      set({ isSending: false });
    }
  },
}));
