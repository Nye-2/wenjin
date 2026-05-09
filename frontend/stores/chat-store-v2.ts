/**
 * Chat Store v2 — Zustand store for chat state management.
 *
 * Key fix over v1 (thread.ts): blocks are stored strictly in **arrival order**.
 * The old store prepended reasoning blocks, which caused the content/reasoning
 * ordering bug described in spec §1.1. Here, thinking blocks stay in position.
 */

import { create } from "zustand";

// ── Data types ──────────────────────────────────────────────────────────────

export type QuestionCardData = {
  question: string;
  options?: string[];
  context?: string;
};

export type ResultCardData = {
  execution_id: string;
  capability_name: string;
  status: "completed" | "partial";
  outputs: Record<string, unknown>;
};

export type ToolInvocationData = {
  tool: string;
  args: Record<string, unknown>;
};

export type ToolResultData = {
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

export type ChatEvent =
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
      data: {
        execution_id: string;
        capability_name: string;
        status: "completed" | "partial";
        outputs: Record<string, unknown>;
        [key: string]: unknown;
      };
    };

// ── Store interface ─────────────────────────────────────────────────────────

interface ChatState {
  messages: Message[];
  currentAssistantId: string | null;
  handleEvent(event: ChatEvent): void;
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
}));
