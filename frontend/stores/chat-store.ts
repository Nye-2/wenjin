/**
 * Chat Store — Zustand store for chat state management.
 * Blocks stored strictly in arrival order.
 */

import { create } from "zustand";
import { authorizedFetch } from "@/lib/api/client";
import type {
  QuestionCardBlock,
  ResultCardBlock,
  StatusLineBlock,
  TextBlock,
} from "@/lib/api/blocks";
import type { WorkspacePrismReviewItem } from "@/lib/api/types";

// ── Data types ──────────────────────────────────────────────────────────────

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
  review_items?: WorkspacePrismReviewItem[];
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
  | TextBlock
  | { kind: "thinking"; content: string }
  | StatusLineBlock
  | QuestionCardBlock
  | ResultCardBlock
  | { kind: "result_card"; data: ResultCardData }
  | { kind: "tool_invocation"; data: ToolInvocationData }
  | { kind: "tool_result"; data: ToolResultData };

export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  blocks: Block[];
  createdAt: string;
  metadata?: Record<string, unknown>;
};

export type SendMessageOptions = {
  skill?: string | null;
  metadata?: Record<string, unknown> | null;
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
  | { type: "chat.assistant.finalize_block"; block: Block }
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
  /** Tracks assistant message IDs that have received their first post-stream
   *  block — subsequent finalize_block events append, the first one replaces. */
  finalizedMessageIds: Set<string>;
  handleEvent(event: ChatEvent): void;
  loadHistory(workspaceId: string): Promise<string | null>;
  sendMessage(
    workspaceId: string,
    content: string,
    attachments?: Array<{ name: string; path: string }>,
    options?: SendMessageOptions,
  ): Promise<void>;
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

function findExecutionMessageIndex(
  messages: Message[],
  executionId: string,
): number {
  for (let i = messages.length - 1; i >= 0; i--) {
    const metadata = messages[i].metadata;
    if (!metadata || typeof metadata !== "object") {
      continue;
    }
    const orchestration = (metadata as Record<string, unknown>).orchestration;
    if (!orchestration || typeof orchestration !== "object") {
      continue;
    }
    const candidateExecutionId = (orchestration as Record<string, unknown>).execution_id;
    if (candidateExecutionId === executionId) {
      return i;
    }
  }
  return -1;
}

// ── Store implementation ────────────────────────────────────────────────────

export const useChatStoreV2 = create<ChatState>((set, get) => ({
  messages: [],
  currentAssistantId: null,
  isSending: false,
  finalizedMessageIds: new Set<string>(),

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
          metadata:
            typeof event.data.metadata === "object" && event.data.metadata
              ? (event.data.metadata as Record<string, unknown>)
              : undefined,
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
          const lastBlock = msg.blocks[msg.blocks.length - 1];

          // Merge consecutive text blocks (streamed token-by-token from backend)
          if (
            event.block.kind === "text" &&
            lastBlock?.kind === "text"
          ) {
            const updatedBlocks = [...msg.blocks];
            updatedBlocks[updatedBlocks.length - 1] = {
              ...lastBlock,
              content: lastBlock.content + event.block.content,
            };
            const updatedMessages = [...state.messages];
            updatedMessages[idx] = { ...msg, blocks: updatedBlocks };
            return { messages: updatedMessages };
          }

          const updatedMessages = [...state.messages];
          updatedMessages[idx] = {
            ...msg,
            blocks: [...msg.blocks, event.block],
          };
          return { messages: updatedMessages };
        });
        break;
      }

      // ── Finalize block (post-stream authoritative blocks) ─────────────
      case "chat.assistant.finalize_block": {
        const { currentAssistantId, finalizedMessageIds } = get();
        if (!currentAssistantId) break;

        set((state) => {
          const idx = findAssistantMessageIndex(
            state.messages,
            currentAssistantId,
          );
          if (idx === -1) return state;

          const msg = state.messages[idx];
          const updatedMessages = [...state.messages];

          // First finalize_block for this message: replace streamed blocks
          if (!finalizedMessageIds.has(currentAssistantId)) {
            updatedMessages[idx] = {
              ...msg,
              blocks: [event.block],
            };
            const newFinalized = new Set(finalizedMessageIds);
            newFinalized.add(currentAssistantId);
            return {
              messages: updatedMessages,
              finalizedMessageIds: newFinalized,
            };
          }

          // Subsequent finalize_blocks: append
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
          const idxByExecution = findExecutionMessageIndex(
            state.messages,
            event.data.execution_id,
          );
          const idx =
            idxByExecution !== -1
              ? idxByExecution
              : findAssistantMessageIndex(
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
    set({
      messages: [],
      currentAssistantId: null,
      finalizedMessageIds: new Set<string>(),
    });
  },

  async loadHistory(workspaceId: string): Promise<string | null> {
    const { messages } = get();
    if (messages.length > 0) return null; // already loaded

    try {
      const res = await authorizedFetch(
        `/api/workspaces/${workspaceId}/thread`,
        { method: "POST", headers: { "Content-Type": "application/json" } },
      );
      if (!res.ok) return null;
      const thread = await res.json();

      if (thread.messages && thread.messages.length > 0) {
        const loaded: Message[] = thread.messages.map((m: Record<string, unknown>) => ({
          id: (m.id as string) || crypto.randomUUID(),
          role: (m.role as "user" | "assistant" | "system") || "assistant",
          blocks: Array.isArray(m.blocks) ? (m.blocks as Block[]) : [{ kind: "text" as const, content: String(m.content || "") }],
          createdAt: (m.created_at as string) || new Date().toISOString(),
          metadata:
            typeof m.metadata === "object" && m.metadata
              ? (m.metadata as Record<string, unknown>)
              : undefined,
        }));
        set({ messages: loaded });
      }
      return thread.id as string;
    } catch {
      return null;
    }
  },

  async sendMessage(
    workspaceId: string,
    content: string,
    attachments: Array<{ name: string; path: string }> = [],
    options: SendMessageOptions = {},
  ) {
    const { isSending } = get();
    if (isSending || !content.trim()) return;
    set({ isSending: true });

    const userMsgId = crypto.randomUUID();
    get().handleEvent({
      type: "chat.user.message",
      data: {
        id: userMsgId,
        content,
        timestamp: new Date().toISOString(),
        metadata: options.metadata ?? undefined,
      },
    });

    try {
      const threadRequestBody =
        typeof options.skill === "string" && options.skill.trim()
          ? JSON.stringify({ skill: options.skill.trim() })
          : undefined;

      // Ensure thread exists
      const threadRes = await authorizedFetch(
        `/api/workspaces/${workspaceId}/thread`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: threadRequestBody,
        },
      );
      if (!threadRes.ok) throw new Error("Failed to create thread");
      const thread = await threadRes.json();
      const threadId = thread.id;

      // Load existing messages if store is empty (first call after page load)
      if (get().messages.length === 0 && thread.messages?.length > 0) {
        const loaded: Message[] = thread.messages.map((m: Record<string, unknown>) => ({
          id: (m.id as string) || crypto.randomUUID(),
          role: (m.role as "user" | "assistant" | "system") || "assistant",
          blocks: Array.isArray(m.blocks) ? (m.blocks as Block[]) : [{ kind: "text" as const, content: String(m.content || "") }],
          createdAt: (m.created_at as string) || new Date().toISOString(),
          metadata:
            typeof m.metadata === "object" && m.metadata
              ? (m.metadata as Record<string, unknown>)
              : undefined,
        }));
        set({ messages: loaded });
      }

      // Create assistant placeholder
      const assistantMsgId = crypto.randomUUID();
      get().handleEvent({
        type: "chat.assistant.start",
        data: { message_id: assistantMsgId },
      });

      const runPayload: Record<string, unknown> = {
        message: content,
        workspace_id: workspaceId,
        attachments: attachments.map((a) => ({
          name: a.name,
          path: a.path,
          kind: "transient",
        })),
      };
      if (typeof options.skill === "string" && options.skill.trim()) {
        runPayload.skill = options.skill.trim();
      }
      if (options.metadata && typeof options.metadata === "object") {
        runPayload.metadata = options.metadata;
      }

      // Stream run response — backend expects RunCreateRequest { message, ... }
      const res = await authorizedFetch(
        `/api/threads/${threadId}/runs/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(runPayload),
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
                  type: "chat.assistant.finalize_block",
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
                  label: data.error ?? "Unknown error",
                  run_id: "stream-error",
                  tone: "error",
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
