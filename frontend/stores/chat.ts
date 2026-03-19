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
  type Thread,
  type ThreadAgentStatus,
  type ThreadSummary,
} from '../lib/api';

// ============ Types ============

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

// ============ Store State ============

interface ChatState {
  messages: Message[];
  isStreaming: boolean;
  isThreadsLoading: boolean;
  currentSkill: string | null;
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
    }
  ) => Promise<void>;
  addMessage: (message: Message) => void;
  loadThreads: (workspaceId: string) => Promise<ThreadSummary[]>;
  loadLatestThread: (workspaceId: string) => Promise<void>;
  loadThread: (threadId: string) => Promise<void>;
  deleteThread: (threadId: string, workspaceId: string) => Promise<void>;
  upsertThreadSummary: (summary: ThreadSummary) => void;
  removeThread: (threadId: string) => void;
  setThreadStatus: (status: ThreadAgentStatus) => void;
  startNewThread: () => void;
  setCurrentSkill: (skill: string | null) => void;
  clearMessages: () => void;
  setThreadId: (threadId: string | null) => void;
}

function toStoreMessages(detail: Thread): Message[] {
  return detail.messages
    .filter(
      (message): message is typeof message & { role: 'user' | 'assistant' } =>
        message.role === 'user' || message.role === 'assistant'
    )
    .map((message, index) => ({
      id: `${detail.id}:${index}`,
      role: message.role,
      content: message.content,
      created_at: message.timestamp ?? detail.updated_at,
    }));
}

function buildThreadPreview(messages: Thread['messages']) {
  const lastMessage = messages[messages.length - 1];
  const normalizedPreview = typeof lastMessage?.content === 'string'
    ? lastMessage.content.replace(/\s+/g, ' ').trim()
    : '';

  return {
    message_count: messages.length,
    last_message_role: lastMessage?.role ?? null,
    last_message_preview: normalizedPreview
      ? normalizedPreview.length <= 120
        ? normalizedPreview
        : `${normalizedPreview.slice(0, 117).trimEnd()}...`
      : null,
  };
}

function toThreadSummary(thread: Thread | ThreadSummary): ThreadSummary {
  if ('messages' in thread) {
    return {
      id: thread.id,
      workspace_id: thread.workspace_id,
      title: thread.title ?? null,
      model: thread.model,
      skill: thread.skill ?? null,
      created_at: thread.created_at,
      updated_at: thread.updated_at,
      ...buildThreadPreview(thread.messages),
    };
  }

  return thread;
}

function upsertThreadSummary(threads: ThreadSummary[], summary: ThreadSummary): ThreadSummary[] {
  return [summary, ...threads.filter((thread) => thread.id !== summary.id)].sort(
    (left, right) =>
      new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()
  );
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isStreaming: false,
  isThreadsLoading: false,
  currentSkill: null,
  threadId: null,
  threads: [],
  threadStatuses: {},
  error: null,

  sendMessage: async (content: string, options) => {
    const { threadId, currentSkill } = get();
    const hasExplicitSkill = Boolean(options && "skill" in options);
    const skillToUse = hasExplicitSkill ? (options?.skill ?? null) : currentSkill;

    // Generate unique ID for user message
    const userMessageId = `user-${Date.now()}`;
    const userMessage: Message = {
      id: userMessageId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };

    // Add user message immediately
    set((state) => ({
      messages: [...state.messages, userMessage],
      isStreaming: true,
      error: null,
    }));

    // Prepare placeholder for assistant message
    const assistantMessageId = `assistant-${Date.now()}`;
    let assistantContent = '';
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, assistantMessage],
    }));

    const requestPayload = {
      message: content,
      workspace_id: options?.workspaceId,
      thread_id: threadId || undefined,
      model: options?.model,
      ...(hasExplicitSkill ? { skill: skillToUse } : currentSkill ? { skill: currentSkill } : {}),
    };

    // Stream response
    streamChat(
      requestPayload,
      // onMessage - receive content chunks
      (chunk) => {
        assistantContent += chunk;
        set((state) => {
          const messages = [...state.messages];
          const lastIndex = messages.length - 1;
          if (lastIndex >= 0 && messages[lastIndex].role === 'assistant') {
            messages[lastIndex] = {
              ...messages[lastIndex],
              content: assistantContent,
            };
          }
          return { messages };
        });
      },
      // onThreadId - receive thread ID
      ({ threadId: newThreadId, skill }) => {
        set((state) => ({
          threadId: newThreadId,
          currentSkill: skill,
          threads: state.threads.some((thread) => thread.id === newThreadId)
            ? state.threads
            : upsertThreadSummary(state.threads, {
                id: newThreadId,
                workspace_id: options?.workspaceId,
                title: null,
                model: options?.model ?? "default",
                skill,
                message_count: state.messages.length + 1,
                last_message_role: 'assistant',
                last_message_preview: null,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              }),
        }));
      },
      // onError
      (error) => {
        set({ error, isStreaming: false });
      },
      // onDone
      () => {
        set({ isStreaming: false });
        if (options?.workspaceId) {
          void get().loadThreads(options.workspaceId);
        }
      }
    );

    if (hasExplicitSkill) {
      set({ currentSkill: skillToUse });
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
        threadId: null,
        threads: [],
        error: null,
      });
      return;
    }

    await get().loadThread(threads[0].id);
  },

  loadThread: async (threadId: string) => {
    try {
      const detail = await getThread(threadId);
      const summary = toThreadSummary(detail);

      set((state) => ({
        messages: toStoreMessages(detail),
        currentSkill: detail.skill ?? null,
        threadId: detail.id,
        threads: upsertThreadSummary(state.threads, summary),
        error: null,
      }));
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
    set((state) => ({
      threads: upsertThreadSummary(state.threads, summary),
      currentSkill:
        state.threadId === summary.id
          ? summary.skill ?? state.currentSkill
          : state.currentSkill,
    }));
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
      threadId: null,
      threadStatuses: {},
      error: null,
    });
  },

  setCurrentSkill: (skill: string | null) => {
    set({ currentSkill: skill });
  },

  clearMessages: () => {
    set({
      messages: [],
      currentSkill: null,
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
