/**
 * Chat Store for AcademiaGPT
 * Manages chat messages and streaming state
 */

import { create } from 'zustand';
import {
  deleteThread as deleteThreadRequest,
  getThread,
  listThreads,
  streamChat,
  type ReasoningEffort,
  type ThreadAgentStatus,
  type ThreadSummary,
} from '../lib/api';
import { syncCurrentSkillWithThread } from '@/lib/chat-skill-state';
import { upsertThreadSummaryList } from '@/lib/workspace-event-ordering';
import {
  buildPendingThreadSummary,
  createPendingUserMessage,
  createPlaceholderAssistantMessage,
  createStoreAssistantMessage,
  findLastAssistantMessage,
  maybeStartStructuredTask,
  toStoreMessages,
  toThreadSummary,
  upsertTrailingAssistantMessage,
  appendAssistantContent,
  type Message,
} from './chat-store-support';

export type { Message } from './chat-store-support';

// ============ Store State ============

interface ChatState {
  messages: Message[];
  isStreaming: boolean;
  isThreadsLoading: boolean;
  currentSkill: string | null;
  isSkillSelectionPending: boolean;
  threadId: string | null;
  threads: ThreadSummary[];
  threadStatuses: Record<string, ThreadAgentStatus>;
  error: string | null;

  // Actions
  sendMessage: (
    content: string,
    options?: {
      workspaceId?: string;
      skill?: string | null;
      model?: string;
      reasoningEffort?: ReasoningEffort;
    }
  ) => Promise<void>;
  addMessage: (message: Message) => void;
  loadThreads: (workspaceId: string) => Promise<ThreadSummary[]>;
  loadLatestThread: (workspaceId: string) => Promise<void>;
  loadThread: (
    threadId: string,
    options?: { preservePendingSkill?: boolean }
  ) => Promise<void>;
  deleteThread: (threadId: string, workspaceId: string) => Promise<void>;
  upsertThreadSummary: (summary: ThreadSummary) => void;
  removeThread: (threadId: string) => void;
  setThreadStatus: (status: ThreadAgentStatus) => void;
  startNewThread: () => void;
  setCurrentSkill: (skill: string | null) => void;
  clearMessages: () => void;
  setThreadId: (threadId: string | null) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isStreaming: false,
  isThreadsLoading: false,
  currentSkill: null,
  isSkillSelectionPending: false,
  threadId: null,
  threads: [],
  threadStatuses: {},
  error: null,

  sendMessage: async (content: string, options) => {
    const { threadId, currentSkill } = get();
    const hasExplicitSkill = Boolean(options && "skill" in options);
    const skillToUse = hasExplicitSkill ? (options?.skill ?? null) : currentSkill;

    const userMessageId = `user-${Date.now()}`;
    const userMessage = createPendingUserMessage({
      id: userMessageId,
      content,
      createdAt: new Date().toISOString(),
    });

    set((state) => ({
      messages: [...state.messages, userMessage],
      isStreaming: true,
      error: null,
    }));

    const assistantMessageId = `assistant-${Date.now()}`;
    let assistantContent = '';
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
      thread_id: threadId || undefined,
      model: options?.model,
      reasoning_effort: options?.reasoningEffort,
      ...(hasExplicitSkill ? { skill: skillToUse } : currentSkill ? { skill: currentSkill } : {}),
    };

    // Stream response
    streamChat(
      requestPayload,
      (chunk) => {
        assistantContent += chunk;
        set((state) => ({
          messages: appendAssistantContent(state.messages, assistantContent),
        }));
      },
      ({ threadId: newThreadId, skill }) => {
        const createdAt = new Date().toISOString();
        set((state) => ({
          threadId: newThreadId,
          currentSkill: skill,
          isSkillSelectionPending: false,
          threads: state.threads.some((thread) => thread.id === newThreadId)
            ? state.threads
            : upsertThreadSummaryList(
                state.threads,
                buildPendingThreadSummary({
                  threadId: newThreadId,
                  workspaceId: options?.workspaceId,
                  model: options?.model,
                  skill,
                  messageCount: state.messages.length + 1,
                  createdAt,
                })
              ),
        }));
      },
      (assistantMessage) => {
        const hydratedMessage = createStoreAssistantMessage({
          fallbackId: assistantMessageId,
          fallbackCreatedAt: new Date().toISOString(),
          message: assistantMessage,
        });
        set((state) => ({
          messages: upsertTrailingAssistantMessage(state.messages, hydratedMessage),
        }));
        maybeStartStructuredTask(hydratedMessage);
      },
      (error) => {
        set({ error, isStreaming: false });
      },
      () => {
        set({ isStreaming: false });
        if (options?.workspaceId) {
          void get().loadThreads(options.workspaceId);
        }
      }
    );

    if (hasExplicitSkill) {
      set({
        currentSkill: skillToUse,
        isSkillSelectionPending: true,
      });
    }
  },

  addMessage: (message: Message) => {
    set((state) => ({
      messages: [...state.messages, message],
    }));
  },

  loadThreads: async (workspaceId: string) => {
    set({ isThreadsLoading: true });
    try {
      const { threads } = await listThreads(workspaceId, 20);
      set((state) => {
        const activeThreadStillVisible = state.threadId
          ? threads.some((thread) => thread.id === state.threadId)
          : true;
        return {
          threads,
          isThreadsLoading: false,
          ...(activeThreadStillVisible
            ? {}
            : {
                messages: [],
                currentSkill: null,
                isSkillSelectionPending: false,
                threadId: null,
              }),
          error: null,
        };
      });
      return threads;
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load chat threads',
        isThreadsLoading: false,
      });
      return [];
    }
  },

  loadLatestThread: async (workspaceId: string) => {
    const threads = await get().loadThreads(workspaceId);
    if (threads.length === 0) {
      set({
        messages: [],
        currentSkill: null,
        isSkillSelectionPending: false,
        threadId: null,
        threads: [],
        error: null,
      });
      return;
    }

    await get().loadThread(threads[0].id);
  },

  loadThread: async (threadId: string, options) => {
    try {
      const detail = await getThread(threadId);
      const summary = toThreadSummary(detail);
      const messages = toStoreMessages(detail);

      set((state) => {
        const nextSkillState =
          options?.preservePendingSkill
            ? syncCurrentSkillWithThread({
                currentSkill: state.currentSkill,
                nextThreadSkill: detail.skill ?? null,
                isSkillSelectionPending: state.isSkillSelectionPending,
              })
            : {
                currentSkill: detail.skill ?? null,
                isSkillSelectionPending: false,
              };

        return {
          messages,
          currentSkill: nextSkillState.currentSkill,
          isSkillSelectionPending: nextSkillState.isSkillSelectionPending,
          threadId: detail.id,
          threads: upsertThreadSummaryList(state.threads, summary),
          error: null,
        };
      });
      const lastAssistantMessage = findLastAssistantMessage(messages);
      if (lastAssistantMessage) {
        maybeStartStructuredTask(lastAssistantMessage);
      }
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to load chat thread',
      });
    }
  },

  deleteThread: async (threadId: string, workspaceId: string) => {
    try {
      await deleteThreadRequest(threadId);
      const state = get();
      const remainingThreads = state.threads.filter((thread) => thread.id !== threadId);

      set({
        threads: remainingThreads,
        error: null,
      });

      if (state.threadId !== threadId) {
        return;
      }

      if (remainingThreads.length > 0) {
        await get().loadThread(remainingThreads[0].id);
        return;
      }

      const refreshedThreads = await get().loadThreads(workspaceId);
      if (refreshedThreads.length > 0) {
        await get().loadThread(refreshedThreads[0].id);
      } else {
        get().startNewThread();
      }
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to delete chat thread',
      });
      throw error;
    }
  },

  upsertThreadSummary: (summary: ThreadSummary) => {
    set((state) => {
      if (state.threadId !== summary.id) {
        return {
          threads: upsertThreadSummaryList(state.threads, summary),
        };
      }

      const nextSkillState = syncCurrentSkillWithThread({
        currentSkill: state.currentSkill,
        nextThreadSkill: summary.skill ?? null,
        isSkillSelectionPending: state.isSkillSelectionPending,
      });

      return {
        threads: upsertThreadSummaryList(state.threads, summary),
        currentSkill: nextSkillState.currentSkill,
        isSkillSelectionPending: nextSkillState.isSkillSelectionPending,
      };
    });
  },

  removeThread: (threadId: string) => {
    set((state) => {
      const remainingThreads = state.threads.filter((thread) => thread.id !== threadId);
      const nextState: Partial<ChatState> = {
        threads: remainingThreads,
      };

      if (state.threadId === threadId) {
        nextState.threadId = null;
        nextState.currentSkill = null;
        nextState.isSkillSelectionPending = false;
        nextState.messages = [];
      }

      const restStatuses = { ...state.threadStatuses };
      delete restStatuses[threadId];
      nextState.threadStatuses = restStatuses;
      return nextState;
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

  startNewThread: () => {
    set({
      messages: [],
      currentSkill: null,
      isSkillSelectionPending: false,
      threadId: null,
      threadStatuses: {},
      error: null,
    });
  },

  setCurrentSkill: (skill: string | null) => {
    set({
      currentSkill: skill,
      isSkillSelectionPending: true,
    });
  },

  clearMessages: () => {
    set({
      messages: [],
      currentSkill: null,
      isSkillSelectionPending: false,
      threadId: null,
      threads: [],
      threadStatuses: {},
      error: null,
    });
  },

  setThreadId: (threadId: string | null) => {
    set({ threadId });
  },
}));

export default useChatStore;
