/**
 * Chat Store for Wenjin (问津)
 * Manages chat messages and streaming state
 */

import { create } from 'zustand';
import {
  ensureWorkspaceChatThread,
  streamChat,
  type ChatAttachment,
  type ReasoningEffort,
  type ThreadAgentStatus,
  type ThreadSummary,
} from '../lib/api';
import {
  createCommittedSkillState,
  createPendingSkillSelection,
  syncCurrentSkillWithThread,
} from '@/lib/chat-skill-state';
import {
  buildPendingThreadSummary,
  createPendingUserMessage,
  createPlaceholderAssistantMessage,
  createStoreAssistantMessage,
  findLastAssistantMessage,
  maybeStartStructuredTask,
  removeTrailingEmptyAssistantMessage,
  removeTrailingPendingAssistantMessage,
  syncAttachmentExtractionsWithTask,
  toStoreMessages,
  toThreadSummary,
  upsertTrailingAssistantReasoning,
  upsertTrailingAssistantMessage,
  appendAssistantContent,
  type Message,
} from './chat-store-support';

export type { Message } from './chat-store-support';

// ============ Store State ============

interface ChatState {
  messages: Message[];
  isStreaming: boolean;
  isWorkspaceThreadLoading: boolean;
  isThreadLoading: boolean;
  currentSkill: string | null;
  threadSkill: string | null;
  activeSkill: string | null;
  isSkillSelectionPending: boolean;
  threadId: string | null;
  currentThreadSummary: ThreadSummary | null;
  threadStatuses: Record<string, ThreadAgentStatus>;
  error: string | null;
  _abortStream: (() => void) | null;

  // Actions
  sendMessage: (
    content: string,
    options?: {
      workspaceId?: string;
      skill?: string | null;
      model?: string;
      reasoningEffort?: ReasoningEffort;
      threadId?: string;
      attachments?: ChatAttachment[];
      metadata?: Record<string, unknown>;
    }
  ) => void;
  abortStream: () => void;
  addMessage: (message: Message) => void;
  ensureWorkspaceThread: (
    workspaceId: string,
    options?: {
      model?: string;
      skill?: string | null;
      preservePendingSkill?: boolean;
      forceRefresh?: boolean;
    }
  ) => Promise<string | null>;
  refreshCurrentThread: (
    workspaceId: string,
    options?: {
      model?: string;
      skill?: string | null;
      preservePendingSkill?: boolean;
    }
  ) => Promise<boolean>;
  syncCurrentThreadSummary: (summary: ThreadSummary) => void;
  clearCurrentThread: () => void;
  setThreadStatus: (status: ThreadAgentStatus) => void;
  syncAttachmentExtractionTask: (
    task: import("@/lib/api").WorkspaceTaskEvent["task"]
  ) => void;
  startNewThread: () => void;
  setCurrentSkill: (skill: string | null) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isStreaming: false,
  isWorkspaceThreadLoading: false,
  isThreadLoading: false,
  currentSkill: null,
  threadSkill: null,
  activeSkill: null,
  isSkillSelectionPending: false,
  threadId: null,
  currentThreadSummary: null,
  threadStatuses: {},
  error: null,
  _abortStream: null,

  abortStream: () => {
    const abort = get()._abortStream;
    if (abort) {
      abort();
      set((state) => ({
        _abortStream: null,
        isStreaming: false,
        messages: removeTrailingPendingAssistantMessage(
          removeTrailingEmptyAssistantMessage(state.messages)
        ),
      }));
    }
  },

  sendMessage: (content: string, options) => {
    // Abort any in-flight stream before starting a new one
    get().abortStream();

    const { threadId, activeSkill, isSkillSelectionPending } = get();
    const effectiveThreadId = options?.threadId || threadId || undefined;
    const hasExplicitSkill = Boolean(options && "skill" in options);
    const skillToUse = hasExplicitSkill
      ? (options?.skill ?? null)
      : activeSkill;
    const shouldSendExplicitSkill = hasExplicitSkill || isSkillSelectionPending;

    const userMessageId = `user-${crypto.randomUUID()}`;
    const userMessage = createPendingUserMessage({
      id: userMessageId,
      content,
      createdAt: new Date().toISOString(),
      attachments: options?.attachments,
      metadata: options?.metadata,
    });

    set((state) => ({
      messages: [...state.messages, userMessage],
      isStreaming: true,
      error: null,
    }));

    const assistantMessageId = `assistant-${crypto.randomUUID()}`;
    let assistantContent = '';
    let assistantReasoning = '';
    let streamAcceptedByServer = false;
    const assistantMessage = createPlaceholderAssistantMessage({
      id: assistantMessageId,
      createdAt: new Date().toISOString(),
    });

    set((state) => ({
      messages: [...state.messages, assistantMessage],
    }));

    const requestPayload = {
      message: content,
      workspace_id: options?.workspaceId,
      thread_id: effectiveThreadId,
      model: options?.model,
      reasoning_effort: options?.reasoningEffort,
      attachments: options?.attachments,
      metadata: options?.metadata,
      ...(shouldSendExplicitSkill ? { skill: skillToUse } : {}),
    };

    // Stream response — capture abort function
    const abort = streamChat(
      requestPayload,
      (chunk) => {
        assistantContent += chunk;
        set((state) => ({
          messages: appendAssistantContent(state.messages, assistantContent),
        }));
      },
      (chunk) => {
        assistantReasoning += chunk;
        set((state) => ({
          messages: upsertTrailingAssistantReasoning(
            state.messages,
            assistantReasoning
          ),
        }));
      },
      ({ threadId: newThreadId, skill, skillName }) => {
        streamAcceptedByServer = true;
        const createdAt = new Date().toISOString();
        set((state) => {
          const nextSkillState = syncCurrentSkillWithThread({
            currentSkill: state.currentSkill,
            nextThreadSkill: skill,
            isSkillSelectionPending: state.isSkillSelectionPending,
          });
          const nextSummary =
            state.currentThreadSummary?.id === newThreadId
              ? {
                  ...state.currentThreadSummary,
                  skill,
                  skill_name: skillName,
                }
              : buildPendingThreadSummary({
                  threadId: newThreadId,
                  workspaceId: options?.workspaceId,
                  model: options?.model,
                  skill,
                  skillName,
                  messageCount: state.messages.length + 1,
                  createdAt,
                });
          return {
            threadId: newThreadId,
            currentSkill: nextSkillState.currentSkill,
            threadSkill: nextSkillState.threadSkill,
            activeSkill: nextSkillState.activeSkill,
            isSkillSelectionPending: nextSkillState.isSkillSelectionPending,
            currentThreadSummary: nextSummary,
          };
        });
      },
      (assistantMessage) => {
        streamAcceptedByServer = true;
        const hydratedMessage = createStoreAssistantMessage({
          fallbackId: assistantMessageId,
          fallbackCreatedAt: new Date().toISOString(),
          message: assistantMessage,
        });
        set((state) => ({
          messages: upsertTrailingAssistantMessage(state.messages, hydratedMessage),
        }));
        const scopedWorkspaceId =
          options?.workspaceId || get().currentThreadSummary?.workspace_id || null;
        maybeStartStructuredTask(hydratedMessage, scopedWorkspaceId);
      },
      (error) => {
        set((state) => {
          const cleanedMessages = removeTrailingPendingAssistantMessage(
            removeTrailingEmptyAssistantMessage(state.messages)
          );
          return {
            error,
            isStreaming: false,
            isSkillSelectionPending: false,
            _abortStream: null,
            messages: streamAcceptedByServer
              ? cleanedMessages
              : cleanedMessages.filter((message) => message.id !== userMessageId),
          };
        });
      },
      () => {
        set({ isStreaming: false, _abortStream: null });
      }
    );

    set({ _abortStream: abort });

    if (hasExplicitSkill) {
      set((state) => ({
        ...createPendingSkillSelection({
          skill: skillToUse,
          threadSkill: state.threadSkill,
        }),
      }));
    }
  },

  addMessage: (message: Message) => {
    set((state) => ({
      messages: [...state.messages, message],
    }));
  },

  ensureWorkspaceThread: async (workspaceId, options) => {
    const state = get();
    if (
      !options?.forceRefresh &&
      state.threadId &&
      state.currentThreadSummary?.workspace_id === workspaceId
    ) {
      return state.threadId;
    }
    const shouldResetMessages = !options?.forceRefresh;
    set(() => ({
      isWorkspaceThreadLoading: true,
      isThreadLoading: true,
      ...(shouldResetMessages ? { messages: [] } : {}),
    }));

    try {
      const detail = await ensureWorkspaceChatThread(workspaceId, {
        model: options?.model,
        skill: options?.skill,
      });
      const summary = toThreadSummary(detail);
      const messages = toStoreMessages(detail);

      const nextSkillState = options?.preservePendingSkill
        ? syncCurrentSkillWithThread({
            currentSkill: get().currentSkill,
            nextThreadSkill: detail.skill ?? null,
            isSkillSelectionPending: get().isSkillSelectionPending,
          })
        : createCommittedSkillState(detail.skill ?? null);

      set({
        messages,
        ...nextSkillState,
        threadId: detail.id,
        currentThreadSummary: summary,
        isWorkspaceThreadLoading: false,
        isThreadLoading: false,
        error: null,
      });
      const lastAssistantMessage = findLastAssistantMessage(messages);
      if (lastAssistantMessage) {
        maybeStartStructuredTask(lastAssistantMessage, workspaceId);
      }
      return detail.id;
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to ensure workspace chat thread',
        isWorkspaceThreadLoading: false,
        isThreadLoading: false,
      });
      return null;
    }
  },

  refreshCurrentThread: async (workspaceId, options) => {
    const threadId = await get().ensureWorkspaceThread(workspaceId, {
      ...options,
      forceRefresh: true,
    });
    return Boolean(threadId);
  },

  syncCurrentThreadSummary: (summary: ThreadSummary) => {
    set((state) => {
      if (state.threadId !== summary.id) {
        return state;
      }

      const nextSkillState = syncCurrentSkillWithThread({
        currentSkill: state.currentSkill,
        nextThreadSkill: summary.skill ?? null,
        isSkillSelectionPending: state.isSkillSelectionPending,
      });

      return {
        currentThreadSummary: summary,
        ...nextSkillState,
      };
    });
  },

  clearCurrentThread: () => {
    set({
      messages: [],
      ...createCommittedSkillState(null),
      threadId: null,
      currentThreadSummary: null,
      isThreadLoading: false,
    });
  },

  setThreadStatus: (status: ThreadAgentStatus) => {
    set((state) => ({
      threadStatuses: {
        ...state.threadStatuses,
        [status.thread_id]: status,
      },
    }));
  },

  syncAttachmentExtractionTask: (task) => {
    if (!task.thread_id) {
      return;
    }

    set((state) => {
      if (state.threadId !== task.thread_id) {
        return state;
      }

      const nextMessages = syncAttachmentExtractionsWithTask(state.messages, task);
      if (nextMessages === state.messages) {
        return state;
      }

      return {
        messages: nextMessages,
      };
    });
  },

  startNewThread: () => {
    get().abortStream();
    set({
      messages: [],
      ...createCommittedSkillState(null),
      threadId: null,
      currentThreadSummary: null,
      threadStatuses: {},
      isThreadLoading: false,
      error: null,
    });
  },

  setCurrentSkill: (skill: string | null) => {
    set((state) => {
      const nextSkillState = createPendingSkillSelection({
        skill,
        threadSkill: state.threadSkill,
      });
      if (
        state.currentSkill === nextSkillState.currentSkill &&
        state.threadSkill === nextSkillState.threadSkill &&
        state.activeSkill === nextSkillState.activeSkill &&
        state.isSkillSelectionPending === nextSkillState.isSkillSelectionPending
      ) {
        return state;
      }
      return nextSkillState;
    });
  },

  clearMessages: () => {
    set({
      messages: [],
      ...createCommittedSkillState(null),
      threadId: null,
      currentThreadSummary: null,
      threadStatuses: {},
      isThreadLoading: false,
      error: null,
    });
  },
}));

export default useChatStore;
