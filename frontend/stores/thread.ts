/**
 * Thread Store for Wenjin (问津)
 * Manages thread messages and streaming state
 */

import { create } from 'zustand';
import {
  ensureWorkspaceThread,
  streamThread,
  type ThreadAttachment,
  type ReasoningEffort,
  type ThreadRuntimeStatus,
  type ThreadSummary,
} from '../lib/api';
import {
  createCommittedSkillState,
  createPendingSkillSelection,
  syncCurrentSkillWithThread,
} from '@/lib/thread-skill-state';
import {
  buildPendingThreadSummary,
  createPendingUserMessage,
  createPlaceholderAssistantMessage,
  createStoreAssistantMessage,
  removeTrailingEmptyAssistantMessage,
  removeTrailingPendingAssistantMessage,
  syncAttachmentExtractionsWithTask,
  toStoreMessages,
  toThreadSummary,
  upsertTrailingAssistantReasoning,
  upsertTrailingAssistantMessage,
  appendAssistantContent,
  type Message,
} from './thread-store-support';

export type { Message } from './thread-store-support';

// ============ Store State ============

interface ThreadState {
  messages: Message[];
  isStreaming: boolean;
  isWorkspaceThreadLoading: boolean;
  isThreadLoading: boolean;
  currentSkill: string | null;
  threadSkill: string | null;
  activeSkill: string | null;
  isSkillSelectionPending: boolean;
  pendingSkillWorkspaceId: string | null;
  threadId: string | null;
  currentThreadSummary: ThreadSummary | null;
  threadStatuses: Record<string, ThreadRuntimeStatus>;
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
      attachments?: ThreadAttachment[];
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
  setThreadStatus: (status: ThreadRuntimeStatus) => void;
  syncAttachmentExtractionTask: (
    task: import("@/lib/api").WorkspaceTaskEvent["task"]
  ) => void;
  startNewThread: () => void;
  setCurrentSkill: (skill: string | null, workspaceId?: string | null) => void;
  clearMessages: () => void;
}

function normalizeWorkspaceId(value: string | null | undefined): string | null {
  const normalized = String(value ?? "").trim();
  return normalized || null;
}

export const useThreadStore = create<ThreadState>((set, get) => ({
  messages: [],
  isStreaming: false,
  isWorkspaceThreadLoading: false,
  isThreadLoading: false,
  currentSkill: null,
  threadSkill: null,
  activeSkill: null,
  isSkillSelectionPending: false,
  pendingSkillWorkspaceId: null,
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

    const {
      threadId,
      activeSkill,
      isSkillSelectionPending,
      currentThreadSummary,
      pendingSkillWorkspaceId,
    } = get();
    const requestedWorkspaceId = normalizeWorkspaceId(options?.workspaceId);
    const currentThreadWorkspaceId = normalizeWorkspaceId(
      currentThreadSummary?.workspace_id
    );
    const canReuseCurrentThread =
      options?.threadId !== undefined ||
      (threadId !== null &&
        (requestedWorkspaceId === null ||
          requestedWorkspaceId === currentThreadWorkspaceId));
    const effectiveThreadId =
      options?.threadId ??
      (canReuseCurrentThread && threadId ? threadId : undefined);
    const hasExplicitSkill = Boolean(options && "skill" in options);
    const skillToUse = hasExplicitSkill
      ? (options?.skill ?? null)
      : activeSkill;
    const shouldForwardPendingSkill =
      isSkillSelectionPending &&
      pendingSkillWorkspaceId !== null &&
      pendingSkillWorkspaceId === requestedWorkspaceId;
    const shouldSendExplicitSkill = hasExplicitSkill || shouldForwardPendingSkill;

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
    const abort = streamThread(
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
            pendingSkillWorkspaceId: nextSkillState.isSkillSelectionPending
              ? state.pendingSkillWorkspaceId
              : null,
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
            pendingSkillWorkspaceId: null,
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
        pendingSkillWorkspaceId: normalizeWorkspaceId(options?.workspaceId),
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
      const detail = await ensureWorkspaceThread(workspaceId, {
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
        pendingSkillWorkspaceId: nextSkillState.isSkillSelectionPending
          ? normalizeWorkspaceId(workspaceId)
          : null,
        threadId: detail.id,
        currentThreadSummary: summary,
        isWorkspaceThreadLoading: false,
        isThreadLoading: false,
        error: null,
      });
      return detail.id;
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to ensure workspace thread',
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

      const currentSummary = state.currentThreadSummary;
      if (
        currentSummary?.id === summary.id &&
        currentSummary.updated_at === summary.updated_at &&
        currentSummary.message_count === summary.message_count &&
        currentSummary.last_message_preview === summary.last_message_preview &&
        currentSummary.last_message_role === summary.last_message_role &&
        currentSummary.skill === summary.skill &&
        currentSummary.skill_name === summary.skill_name &&
        currentSummary.title === summary.title &&
        currentSummary.model === summary.model
      ) {
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
        pendingSkillWorkspaceId: nextSkillState.isSkillSelectionPending
          ? state.pendingSkillWorkspaceId
          : null,
      };
    });
  },

  clearCurrentThread: () => {
    set({
      messages: [],
      ...createCommittedSkillState(null),
      pendingSkillWorkspaceId: null,
      threadId: null,
      currentThreadSummary: null,
      isThreadLoading: false,
    });
  },

  setThreadStatus: (status: ThreadRuntimeStatus) => {
    set((state) => {
      const currentStatus = state.threadStatuses[status.thread_id];
      if (
        currentStatus?.status === status.status &&
        currentStatus?.current_skill === status.current_skill &&
        currentStatus?.current_skill_name === status.current_skill_name &&
        currentStatus?.subagent_count === status.subagent_count
      ) {
        return state;
      }

      return {
        threadStatuses: {
          ...state.threadStatuses,
          [status.thread_id]: status,
        },
      };
    });
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
      pendingSkillWorkspaceId: null,
      threadId: null,
      currentThreadSummary: null,
      threadStatuses: {},
      isThreadLoading: false,
      error: null,
    });
  },

  setCurrentSkill: (skill: string | null, workspaceId?: string | null) => {
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
      return {
        ...nextSkillState,
        pendingSkillWorkspaceId: nextSkillState.isSkillSelectionPending
          ? normalizeWorkspaceId(workspaceId) ??
            normalizeWorkspaceId(state.currentThreadSummary?.workspace_id) ??
            state.pendingSkillWorkspaceId
          : null,
      };
    });
  },

  clearMessages: () => {
    set({
      messages: [],
      ...createCommittedSkillState(null),
      pendingSkillWorkspaceId: null,
      threadId: null,
      currentThreadSummary: null,
      threadStatuses: {},
      isThreadLoading: false,
      error: null,
    });
  },
}));

export default useThreadStore;
