/**
 * Chat Store — Zustand store for chat state management.
 * Blocks stored strictly in arrival order.
 */

import { create } from "zustand";
import { authorizedFetch } from "@/lib/api/client";
import type {
  AgentBlock,
  ToolInvocationBlock,
  ToolResultBlock,
} from "@/lib/api/blocks";
import { normalizeChatBlock } from "@/lib/api/blocks";
import type { WorkspacePrismReviewItem } from "@/lib/api/types";
import type { ReasoningEffort } from "@/lib/api/types";
import { useRunUiStore } from "@/stores/run-ui-store";

// ── Data types ──────────────────────────────────────────────────────────────

const DEFAULT_WORKSPACE_KEY = "__default__";
const EMPTY_MESSAGES: Message[] = [];

export type ResultCardData = {
  execution_id: string;
  capability_name?: string;
  status: "completed" | "failed_partial" | "failed" | "cancelled";
  token_usage?: { input: number; output: number } | null;
  outputs: Array<{
    id: string;
    kind: string;
    preview: string;
    default_checked: boolean;
    data: Record<string, unknown>;
  }>;
  review_items?: WorkspacePrismReviewItem[];
  preview_item_id?: string | null;
  previewItemId?: string | null;
  narrative?: string;
  duration_seconds?: number;
  errors?: Array<{ message: string; phase?: string; task?: string }>;
};

type ToolInvocationData = Omit<ToolInvocationBlock, "kind"> & Record<string, unknown>;
type ToolResultData = Omit<ToolResultBlock, "kind"> & Record<string, unknown>;

type AsyncResultCardBlock = { kind: "result_card"; data: ResultCardData };

export type Block =
  | AgentBlock
  | AsyncResultCardBlock;

export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  blocks: Block[];
  createdAt: string;
  metadata?: Record<string, unknown>;
};

export type SendMessageOptions = {
  skill?: string | null;
  model?: string | null;
  reasoning_effort?: ReasoningEffort | null;
  metadata?: Record<string, unknown> | null;
};

export type SendMessageResult = {
  executionId?: string | null;
  featureId?: string | null;
  status?: string | null;
  toolResult?: ToolResultData | null;
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
  activeWorkspaceId: string | null;
  messagesByWorkspace: Record<string, Message[]>;
  messages: Message[];
  currentAssistantId: string | null;
  isSending: boolean;
  /** Tracks assistant message IDs that have received their first post-stream
   *  block — subsequent finalize_block events append, the first one replaces. */
  finalizedMessageIds: Set<string>;
  setActiveWorkspace(workspaceId: string): void;
  getWorkspaceMessages(workspaceId: string): Message[];
  handleEvent(event: ChatEvent, workspaceId?: string): void;
  loadHistory(workspaceId: string): Promise<string | null>;
  sendMessage(
    workspaceId: string,
    content: string,
    attachments?: Array<{ name: string; path: string }>,
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeStoreBlock(raw: unknown): Block {
  if (
    isRecord(raw) &&
    raw.kind === "result_card" &&
    isRecord(raw.data) &&
    !("run_id" in raw)
  ) {
    return raw as AsyncResultCardBlock;
  }
  return normalizeChatBlock(raw);
}

function normalizeStoreBlocks(rawBlocks: unknown): Block[] {
  return Array.isArray(rawBlocks)
    ? rawBlocks.map((block) => normalizeStoreBlock(block))
    : [];
}

function withoutKind<T extends { kind: string }>(block: T): Omit<T, "kind"> {
  const { kind: _kind, ...rest } = block;
  return rest;
}

function stableInputFingerprint(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableInputFingerprint(item)).join(",")}]`;
  }
  if (isRecord(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableInputFingerprint(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function isSameToolBlock(a: Block, b: Block): boolean {
  if (a.kind !== b.kind) {
    return false;
  }
  if (a.kind === "tool_result" && b.kind === "tool_result") {
    const aToolCallId =
      typeof a.tool_call_id === "string" ? a.tool_call_id.trim() : "";
    const bToolCallId =
      typeof b.tool_call_id === "string" ? b.tool_call_id.trim() : "";
    if (aToolCallId || bToolCallId) {
      return aToolCallId === bToolCallId;
    }
    const aExecutionId =
      typeof a.execution_id === "string" ? a.execution_id.trim() : "";
    const bExecutionId =
      typeof b.execution_id === "string" ? b.execution_id.trim() : "";
    if (aExecutionId || bExecutionId) {
      return aExecutionId === bExecutionId;
    }
    const aFeatureId =
      typeof a.feature_id === "string" ? a.feature_id.trim() : "";
    const bFeatureId =
      typeof b.feature_id === "string" ? b.feature_id.trim() : "";
    if (aFeatureId || bFeatureId) {
      return aFeatureId === bFeatureId && a.status === b.status;
    }
    return (
      a.tool === b.tool &&
      a.status === b.status &&
      stableInputFingerprint(a.output) === stableInputFingerprint(b.output)
    );
  }
  if (a.kind === "tool_invocation" && b.kind === "tool_invocation") {
    const aToolCallId =
      typeof a.tool_call_id === "string" ? a.tool_call_id.trim() : "";
    const bToolCallId =
      typeof b.tool_call_id === "string" ? b.tool_call_id.trim() : "";
    if (aToolCallId || bToolCallId) {
      return aToolCallId === bToolCallId;
    }
    return (
      a.tool === b.tool &&
      stableInputFingerprint(a.input) === stableInputFingerprint(b.input)
    );
  }
  return false;
}

function appendBlockWithoutDuplicate(blocks: Block[], block: Block): Block[] {
  if (
    (block.kind === "tool_invocation" || block.kind === "tool_result") &&
    blocks.some((existing) => isSameToolBlock(existing, block))
  ) {
    return blocks;
  }
  return [...blocks, block];
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
  messages: [],
  currentAssistantId: null,
  isSending: false,
  finalizedMessageIds: new Set<string>(),

  setActiveWorkspace(workspaceId: string) {
    const workspaceKey = normalizeWorkspaceKey(workspaceId);
    set((state) => {
      const currentKey = normalizeWorkspaceKey(state.activeWorkspaceId);
      const messagesByWorkspace = { ...state.messagesByWorkspace };
      if (state.activeWorkspaceId || state.messages.length > 0) {
        messagesByWorkspace[currentKey] = state.messages;
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
      };
    });
  },

  getWorkspaceMessages(workspaceId: string) {
    return readWorkspaceMessages(get(), workspaceId);
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

          // First finalize_block for this message: replace streamed blocks
          if (!finalizedMessageIds.has(currentAssistantId)) {
            const preservedToolBlocks = msg.blocks.filter(
              (block) => block.kind === "tool_invocation" || block.kind === "tool_result",
            );
            updatedMessages[idx] = {
              ...msg,
              blocks: appendBlockWithoutDuplicate(preservedToolBlocks, block),
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

      // ── Tool invocation ───────────────────────────────────────────────
      case "chat.assistant.tool_invocation": {
        const { currentAssistantId } = get();
        const block = normalizeChatBlock({
          kind: "tool_invocation",
          ...event.data,
        }) as ToolInvocationBlock;
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
            blocks: appendBlockWithoutDuplicate(msg.blocks, block),
          };
          return syncActiveMessages(state, updatedMessages);
        });
        break;
      }

      // ── Tool result ───────────────────────────────────────────────────
      case "chat.assistant.tool_result": {
        const { currentAssistantId } = get();
        const block = normalizeChatBlock({
          kind: "tool_result",
          ...event.data,
        }) as ToolResultBlock;
        if (
          block.status === "launched" &&
          typeof block.execution_id === "string" &&
          block.execution_id.trim()
        ) {
          useRunUiStore.getState().markRunLaunching(block.execution_id.trim());
        }
        set((state) => {
          const idx = findAssistantMessageIndex(
            state.messages,
            currentAssistantId,
          );
          if (idx === -1) return state;

          const msg = state.messages[idx];
          const executionId =
            typeof block.execution_id === "string"
              ? block.execution_id.trim()
              : "";
          const metadata =
            executionId
              ? {
                  ...(msg.metadata ?? {}),
                  orchestration: {
                    ...((msg.metadata?.orchestration as Record<string, unknown> | undefined) ?? {}),
                    execution_id: executionId,
                    feature_id: block.feature_id,
                  },
                }
              : msg.metadata;
          const updatedMessages = [...state.messages];
          updatedMessages[idx] = {
            ...msg,
            metadata,
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

      // ── Execution completed (async result card) ───────────────────────
      case "execution.completed": {
        const { currentAssistantId } = get();
        useRunUiStore.getState().markRunCompleted(event.data.execution_id);
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
          return syncActiveMessages(state, updatedMessages);
        });
        break;
      }

      default:
        break;
    }
  },

  reset() {
    set({
      activeWorkspaceId: null,
      messagesByWorkspace: {},
      messages: [],
      isSending: false,
      currentAssistantId: null,
      finalizedMessageIds: new Set<string>(),
    });
  },

  async loadHistory(workspaceId: string): Promise<string | null> {
    const workspaceKey = normalizeWorkspaceKey(workspaceId);
    const state = get();
    const existingMessages = readWorkspaceMessages(state, workspaceId);
    if (existingMessages.length > 0) return null; // already loaded for this workspace

    try {
      const res = await authorizedFetch(
        `/api/workspaces/${workspaceId}/thread`,
        { method: "POST", headers: { "Content-Type": "application/json" } },
      );
      if (!res.ok) return null;
      const thread = await res.json();

      if (thread.messages && thread.messages.length > 0) {
        const loaded: Message[] = thread.messages.map((m: Record<string, unknown>) => {
          const blocks = normalizeStoreBlocks(m.blocks);
          return {
            id: (m.id as string) || crypto.randomUUID(),
            role: (m.role as "user" | "assistant" | "system") || "assistant",
            blocks: blocks.length
              ? blocks
              : [{ kind: "text" as const, content: String(m.content || "") }],
            createdAt: (m.created_at as string) || new Date().toISOString(),
            metadata:
              typeof m.metadata === "object" && m.metadata
                ? (m.metadata as Record<string, unknown>)
                : undefined,
          };
        });
        set((current) => {
          const messagesByWorkspace = {
            ...current.messagesByWorkspace,
            [workspaceKey]: loaded,
          };
          if (current.activeWorkspaceId === workspaceId || !current.activeWorkspaceId) {
            return {
              activeWorkspaceId: workspaceId,
              messages: loaded,
              messagesByWorkspace,
            };
          }
          return { messagesByWorkspace };
        });
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
    get().setActiveWorkspace(workspaceId);
    set({ isSending: true });
    let launchedResult: SendMessageResult | null = null;

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
      const threadRequestPayload: Record<string, string> = {};
      if (typeof options.skill === "string" && options.skill.trim()) {
        threadRequestPayload.skill = options.skill.trim();
      }
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
        },
      );
      if (!threadRes.ok) throw new Error("Failed to create thread");
      const thread = await threadRes.json();
      const threadId = thread.id;

      // Load existing messages if store is empty (first call after page load)
      if (get().getWorkspaceMessages(workspaceId).length === 0 && thread.messages?.length > 0) {
        const loaded: Message[] = thread.messages.map((m: Record<string, unknown>) => {
          const blocks = normalizeStoreBlocks(m.blocks);
          return {
            id: (m.id as string) || crypto.randomUUID(),
            role: (m.role as "user" | "assistant" | "system") || "assistant",
            blocks: blocks.length
              ? blocks
              : [{ kind: "text" as const, content: String(m.content || "") }],
            createdAt: (m.created_at as string) || new Date().toISOString(),
            metadata:
              typeof m.metadata === "object" && m.metadata
                ? (m.metadata as Record<string, unknown>)
                : undefined,
          };
        });
        set((state) => ({
          ...syncActiveMessages(state, loaded),
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
        attachments: attachments.map((a) => ({
          name: a.name,
          path: a.path,
          kind: "transient",
        })),
      };
      if (typeof options.skill === "string" && options.skill.trim()) {
        runPayload.skill = options.skill.trim();
      }
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
                  block: normalizeStoreBlock(data.block),
                });
              }
              break;
            }
            case "tool_invocation": {
              store.handleEvent({
                type: "chat.assistant.tool_invocation",
                data: (data.data ?? {}) as ToolInvocationData,
              });
              break;
            }
            case "tool_result": {
              const toolResultBlock = normalizeChatBlock({
                kind: "tool_result",
                ...((data.data ?? {}) as Record<string, unknown>),
              }) as ToolResultBlock;
              const toolResult = withoutKind(toolResultBlock) as ToolResultData;
              if (
                toolResult.status === "launched" &&
                typeof toolResult.execution_id === "string" &&
                toolResult.execution_id.trim()
              ) {
                launchedResult = {
                  executionId: toolResult.execution_id.trim(),
                  featureId:
                    typeof toolResult.feature_id === "string"
                      ? toolResult.feature_id
                      : null,
                  status: toolResult.status,
                  toolResult,
                };
              } else if (!launchedResult && toolResult.status) {
                launchedResult = {
                  status: toolResult.status,
                  toolResult,
                };
              }
              store.handleEvent({
                type: "chat.assistant.tool_result",
                data: toolResult,
              });
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
      return launchedResult ?? undefined;
    } catch {
      get().handleEvent({ type: "chat.assistant.completion" });
    } finally {
      set({ isSending: false });
    }
  },
}));
