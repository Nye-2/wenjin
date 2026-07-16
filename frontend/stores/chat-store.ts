/**
 * Chat Store — Zustand store for chat state management.
 * Blocks stored strictly in arrival order.
 */

import { create } from "zustand";
import {
  authorizedFetch,
  readErrorMessage,
} from "@/lib/api/client";
import type { AgentBlock } from "@/lib/api/blocks";
import { normalizeChatBlock } from "@/lib/api/blocks";
import type { ThreadAttachment } from "@/lib/api/types";
import type { ReasoningEffort } from "@/lib/reasoning-effort";

// ── Data types ──────────────────────────────────────────────────────────────

const DEFAULT_WORKSPACE_KEY = "__default__";
const EMPTY_MESSAGES: Message[] = [];

export type Block = AgentBlock;

export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  blocks: Block[];
  createdAt: string;
  metadata?: Record<string, unknown>;
};

export type SendMessageOptions = {
  model?: string | null;
  reasoning_effort?: ReasoningEffort | null;
  metadata?: Record<string, unknown> | null;
};

export type SendMessageResult = {
  missionId?: string | null;
  status?: string | null;
  error?: string | null;
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
  | { type: "chat.assistant.completion" };

// ── Store interface ─────────────────────────────────────────────────────────

interface ChatState {
  activeWorkspaceId: string | null;
  messagesByWorkspace: Record<string, Message[]>;
  threadIdsByWorkspace: Record<string, string>;
  messages: Message[];
  currentAssistantId: string | null;
  isSending: boolean;
  activeRequestId: string | null;
  activeRequestWorkspaceId: string | null;
  activeAbortController: AbortController | null;
  /** Tracks assistant message IDs that have received their first post-stream
   *  block — subsequent finalize_block events append, the first one replaces. */
  finalizedMessageIds: Set<string>;
  setActiveWorkspace(workspaceId: string): void;
  getWorkspaceMessages(workspaceId: string): Message[];
  getThreadId(workspaceId: string): string | null;
  handleEvent(event: ChatEvent, workspaceId?: string): void;
  loadHistory(workspaceId: string): Promise<string | null>;
  sendMessage(
    workspaceId: string,
    content: string,
    attachments?: ThreadAttachment[],
    options?: SendMessageOptions,
  ): Promise<SendMessageResult | void>;
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

function normalizeStoreBlock(raw: unknown): Block {
  return normalizeChatBlock(raw);
}

function normalizeStoreBlocks(rawBlocks: unknown): Block[] {
  return Array.isArray(rawBlocks)
    ? rawBlocks.map((block) => normalizeStoreBlock(block))
    : [];
}

function appendBlockWithoutDuplicate(blocks: Block[], block: Block): Block[] {
  return [...blocks, block];
}

function deserializeThreadMessages(rawMessages: unknown): Message[] {
  if (!Array.isArray(rawMessages)) return [];
  return rawMessages.map((raw) => {
    const message = raw as Record<string, unknown>;
    const blocks = normalizeStoreBlocks(message.blocks);
    return {
      id: (message.id as string) || crypto.randomUUID(),
      role:
        (message.role as "user" | "assistant" | "system") || "assistant",
      blocks: blocks.length
        ? blocks
        : [{ kind: "text" as const, content: String(message.content || "") }],
      createdAt:
        (message.created_at as string) || new Date().toISOString(),
      metadata:
        typeof message.metadata === "object" && message.metadata
          ? (message.metadata as Record<string, unknown>)
          : undefined,
    };
  });
}

function mergeMessagesById(existing: Message[], incoming: Message[]): Message[] {
  const seen = new Set(existing.map((message) => message.id));
  return [
    ...incoming.filter((message) => !seen.has(message.id)),
    ...existing,
  ];
}

function isAbortError(error: unknown): boolean {
  return (
    error instanceof DOMException && error.name === "AbortError"
  ) || (error instanceof Error && error.name === "AbortError");
}

function normalizeWorkspaceKey(workspaceId: string | null | undefined): string {
  const trimmed = typeof workspaceId === "string" ? workspaceId.trim() : "";
  return trimmed || DEFAULT_WORKSPACE_KEY;
}

function hasWorkspaceMessages(
  messagesByWorkspace: Record<string, Message[]>,
  workspaceKey: string,
): boolean {
  return Object.prototype.hasOwnProperty.call(messagesByWorkspace, workspaceKey);
}

function readWorkspaceMessages(state: ChatState, workspaceId: string): Message[] {
  const workspaceKey = normalizeWorkspaceKey(workspaceId);
  if (hasWorkspaceMessages(state.messagesByWorkspace, workspaceKey)) {
    return state.messagesByWorkspace[workspaceKey];
  }
  if (!state.activeWorkspaceId || state.activeWorkspaceId === workspaceId) {
    return state.messages;
  }
  return EMPTY_MESSAGES;
}

function syncActiveMessages(
  state: ChatState,
  messages: Message[],
): Pick<ChatState, "messages" | "messagesByWorkspace"> {
  const workspaceKey = normalizeWorkspaceKey(state.activeWorkspaceId);
  return {
    messages,
    messagesByWorkspace: {
      ...state.messagesByWorkspace,
      [workspaceKey]: messages,
    },
  };
}

// ── Store implementation ────────────────────────────────────────────────────

export const useChatStoreV2 = create<ChatState>((set, get) => ({
  activeWorkspaceId: null,
  messagesByWorkspace: {},
  threadIdsByWorkspace: {},
  messages: [],
  currentAssistantId: null,
  isSending: false,
  activeRequestId: null,
  activeRequestWorkspaceId: null,
  activeAbortController: null,
  finalizedMessageIds: new Set<string>(),

  setActiveWorkspace(workspaceId: string) {
    const before = get();
    const switchingWorkspace =
      Boolean(before.activeWorkspaceId) &&
      before.activeWorkspaceId !== workspaceId;
    if (switchingWorkspace) {
      before.activeAbortController?.abort();
    }
    const workspaceKey = normalizeWorkspaceKey(workspaceId);
    set((state) => {
      const currentKey = normalizeWorkspaceKey(state.activeWorkspaceId);
      const messagesByWorkspace = { ...state.messagesByWorkspace };
      const outgoingMessages = switchingWorkspace && state.currentAssistantId
        ? state.messages.filter(
            (message) =>
              message.id !== state.currentAssistantId ||
              message.blocks.length > 0,
          )
        : state.messages;
      if (state.activeWorkspaceId || state.messages.length > 0) {
        messagesByWorkspace[currentKey] = outgoingMessages;
      }
      const shouldPromoteCurrentMessages =
        !state.activeWorkspaceId &&
        state.messages.length > 0 &&
        !hasWorkspaceMessages(messagesByWorkspace, workspaceKey);
      const nextMessages = shouldPromoteCurrentMessages
        ? state.messages
        : messagesByWorkspace[workspaceKey] ?? [];
      if (shouldPromoteCurrentMessages) {
        messagesByWorkspace[workspaceKey] = nextMessages;
      }
      return {
        activeWorkspaceId: workspaceId,
        messages: nextMessages,
        messagesByWorkspace,
        ...(switchingWorkspace
          ? {
              isSending: false,
              currentAssistantId: null,
              activeRequestId: null,
              activeRequestWorkspaceId: null,
              activeAbortController: null,
            }
          : {}),
      };
    });
  },

  getWorkspaceMessages(workspaceId: string) {
    return readWorkspaceMessages(get(), workspaceId);
  },

  getThreadId(workspaceId: string) {
    return get().threadIdsByWorkspace[normalizeWorkspaceKey(workspaceId)] ?? null;
  },

  handleEvent(event: ChatEvent, workspaceId?: string) {
    if (workspaceId) {
      get().setActiveWorkspace(workspaceId);
    }
    switch (event.type) {
      // ── User message ──────────────────────────────────────────────────
      case "chat.user.message": {
        const blocks: Block[] = event.data.blocks?.length
          ? event.data.blocks.map((block) => normalizeStoreBlock(block))
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

        set((state) => syncActiveMessages(state, [...state.messages, message]));
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
          ...syncActiveMessages(state, [...state.messages, message]),
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
              text: lastBlock.text + event.delta,
            };
            const updatedMessages = [...state.messages];
            updatedMessages[idx] = { ...msg, blocks: updatedBlocks };
            return syncActiveMessages(state, updatedMessages);
          }

          // Otherwise create a new thinking block — preserves arrival order
          const updatedMessages = [...state.messages];
          updatedMessages[idx] = {
            ...msg,
            blocks: [
              ...msg.blocks,
              { kind: "thinking", text: event.delta },
            ],
          };
          return syncActiveMessages(state, updatedMessages);
        });
        break;
      }

      // ── Generic block ─────────────────────────────────────────────────
      case "chat.assistant.block": {
        const { currentAssistantId } = get();
        const block = normalizeStoreBlock(event.block);
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
            block.kind === "text" &&
            lastBlock?.kind === "text"
          ) {
            const updatedBlocks = [...msg.blocks];
            updatedBlocks[updatedBlocks.length - 1] = {
              ...lastBlock,
              content: lastBlock.content + block.content,
            };
            const updatedMessages = [...state.messages];
            updatedMessages[idx] = { ...msg, blocks: updatedBlocks };
            return syncActiveMessages(state, updatedMessages);
          }

          const updatedMessages = [...state.messages];
          updatedMessages[idx] = {
            ...msg,
            blocks: appendBlockWithoutDuplicate(msg.blocks, block),
          };
          return syncActiveMessages(state, updatedMessages);
        });
        break;
      }

      // ── Finalize block (post-stream authoritative blocks) ─────────────
      case "chat.assistant.finalize_block": {
        const { currentAssistantId, finalizedMessageIds } = get();
        if (!currentAssistantId) break;
        const block = normalizeStoreBlock(event.block);

        set((state) => {
          const idx = findAssistantMessageIndex(
            state.messages,
            currentAssistantId,
          );
          if (idx === -1) return state;

          const msg = state.messages[idx];
          const updatedMessages = [...state.messages];

          // First finalize_block for this message replaces streamed deltas.
          if (!finalizedMessageIds.has(currentAssistantId)) {
            updatedMessages[idx] = {
              ...msg,
              blocks: [block],
            };
            const newFinalized = new Set(finalizedMessageIds);
            newFinalized.add(currentAssistantId);
            return {
              messages: updatedMessages,
              messagesByWorkspace: {
                ...state.messagesByWorkspace,
                [normalizeWorkspaceKey(state.activeWorkspaceId)]: updatedMessages,
              },
              finalizedMessageIds: newFinalized,
            };
          }

          // Subsequent finalize_blocks: append
          updatedMessages[idx] = {
            ...msg,
            blocks: appendBlockWithoutDuplicate(msg.blocks, block),
          };
          return syncActiveMessages(state, updatedMessages);
        });
        break;
      }

      // ── Completion ────────────────────────────────────────────────────
      case "chat.assistant.completion": {
        set({ currentAssistantId: null });
        break;
      }

      default:
        break;
    }
  },

  reset() {
    get().activeAbortController?.abort();
    set({
      activeWorkspaceId: null,
      messagesByWorkspace: {},
      threadIdsByWorkspace: {},
      messages: [],
      isSending: false,
      currentAssistantId: null,
      activeRequestId: null,
      activeRequestWorkspaceId: null,
      activeAbortController: null,
      finalizedMessageIds: new Set<string>(),
    });
  },

  async loadHistory(workspaceId: string): Promise<string | null> {
    const workspaceKey = normalizeWorkspaceKey(workspaceId);
    const state = get();
    const cachedThreadId = state.threadIdsByWorkspace[workspaceKey];
    if (cachedThreadId) return cachedThreadId;
    const shouldHydrateMessages =
      readWorkspaceMessages(state, workspaceId).length === 0;

    try {
      const res = await authorizedFetch(
        `/api/workspaces/${workspaceId}/thread`,
        { method: "POST", headers: { "Content-Type": "application/json" } },
      );
      if (!res.ok) return null;
      const thread = await res.json();
      const threadId = typeof thread.id === "string" ? thread.id : "";
      if (!threadId) return null;
      const loaded = shouldHydrateMessages
        ? deserializeThreadMessages(thread.messages)
        : null;
      set((current) => {
        const threadIdsByWorkspace = {
          ...current.threadIdsByWorkspace,
          [workspaceKey]: threadId,
        };
        if (loaded === null) return { threadIdsByWorkspace };
        const messagesByWorkspace = {
          ...current.messagesByWorkspace,
          [workspaceKey]: loaded,
        };
        if (
          current.activeWorkspaceId === workspaceId ||
          !current.activeWorkspaceId
        ) {
          return {
            activeWorkspaceId: workspaceId,
            messages: loaded,
            messagesByWorkspace,
            threadIdsByWorkspace,
          };
        }
        return { messagesByWorkspace, threadIdsByWorkspace };
      });
      return threadId;
    } catch {
      return null;
    }
  },

  async sendMessage(
    workspaceId: string,
    content: string,
    attachments: ThreadAttachment[] = [],
    options: SendMessageOptions = {},
  ) {
    const { isSending } = get();
    if (isSending || !content.trim()) return;
    get().setActiveWorkspace(workspaceId);
    const requestId = crypto.randomUUID();
    const abortController = new AbortController();
    const hadWorkspaceMessages =
      get().getWorkspaceMessages(workspaceId).length > 0;
    set({
      isSending: true,
      activeRequestId: requestId,
      activeRequestWorkspaceId: workspaceId,
      activeAbortController: abortController,
    });
    let launchedResult: SendMessageResult | null = null;
    const isCurrentRequest = () => {
      const state = get();
      return (
        state.activeRequestId === requestId &&
        state.activeRequestWorkspaceId === workspaceId &&
        state.activeWorkspaceId === workspaceId
      );
    };

    const userMsgId = crypto.randomUUID();
    get().handleEvent({
      type: "chat.user.message",
      data: {
        id: userMsgId,
        content,
        timestamp: new Date().toISOString(),
        metadata: {
          ...(options.metadata ?? {}),
          ...(attachments.length > 0 ? { attachments } : {}),
        },
      },
    });

    try {
      const threadRequestPayload: Record<string, string> = {};
      if (typeof options.model === "string" && options.model.trim()) {
        threadRequestPayload.model = options.model.trim();
      }
      const threadRequestBody =
        Object.keys(threadRequestPayload).length > 0
          ? JSON.stringify(threadRequestPayload)
          : undefined;

      // Ensure thread exists
      const threadRes = await authorizedFetch(
        `/api/workspaces/${workspaceId}/thread`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: threadRequestBody,
          signal: abortController.signal,
        },
      );
      if (!isCurrentRequest()) return;
      if (!threadRes.ok) {
        throw new Error(
          await readErrorMessage(threadRes, "无法连接对话，请稍后重试"),
        );
      }
      const thread = await threadRes.json();
      if (!isCurrentRequest()) return;
      const threadId = typeof thread.id === "string" ? thread.id : "";
      if (!threadId) throw new Error("对话线程无效，请稍后重试");
      const workspaceKey = normalizeWorkspaceKey(workspaceId);
      set((state) => ({
        threadIdsByWorkspace: {
          ...state.threadIdsByWorkspace,
          [workspaceKey]: threadId,
        },
      }));

      if (!hadWorkspaceMessages && Array.isArray(thread.messages)) {
        const loaded = deserializeThreadMessages(thread.messages);
        set((state) => ({
          ...syncActiveMessages(
            state,
            mergeMessagesById(state.messages, loaded),
          ),
        }));
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
        attachments,
      };
      if (typeof options.model === "string" && options.model.trim()) {
        runPayload.model = options.model.trim();
      }
      if (
        typeof options.reasoning_effort === "string" &&
        options.reasoning_effort.trim()
      ) {
        runPayload.reasoning_effort = options.reasoning_effort.trim();
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
          signal: abortController.signal,
        },
      );

      if (!isCurrentRequest()) return;
      if (!res.ok) {
        throw new Error(
          await readErrorMessage(res, "对话未能启动，请稍后重试"),
        );
      }
      if (!res.body) throw new Error("No response body");

      // Parse SSE from fetch response
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let frameData: string[] = [];
      let frameEvent: string | null = null;

      const flushFrame = () => {
        if (!isCurrentRequest()) {
          frameData = [];
          frameEvent = null;
          return;
        }
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
                const block = normalizeStoreBlock(data.block);
                store.handleEvent({
                  type: "chat.assistant.finalize_block",
                  block,
                });
                if (
                  block.kind === "status_line" &&
                  block.action === "start_mission" &&
                  block.run_id.trim()
                ) {
                  launchedResult = {
                    missionId: block.run_id.trim(),
                    status: "launched",
                  };
                }
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
        if (!isCurrentRequest()) return;
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

      if (!isCurrentRequest()) return;
      get().handleEvent({ type: "chat.assistant.completion" });
      return launchedResult ?? undefined;
    } catch (error: unknown) {
      if (!isCurrentRequest() || isAbortError(error)) {
        return;
      }
      if (!get().currentAssistantId) {
        get().handleEvent({
          type: "chat.assistant.start",
          data: { message_id: crypto.randomUUID() },
        });
      }
      const message =
        error instanceof Error && error.message.trim()
          ? error.message.trim()
          : "消息未能发送，请稍后重试";
      get().handleEvent({
        type: "chat.assistant.block",
        block: {
          kind: "status_line",
          label: message,
          run_id: "chat-send-error",
          tone: "error",
        },
      });
      get().handleEvent({ type: "chat.assistant.completion" });
      return { status: "failed", error: message };
    } finally {
      if (get().activeRequestId === requestId) {
        set({
          isSending: false,
          activeRequestId: null,
          activeRequestWorkspaceId: null,
          activeAbortController: null,
        });
      }
    }
  },
}));
