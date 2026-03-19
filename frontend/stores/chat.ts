/**
 * Chat Store for AcademiaGPT
 * Manages chat messages and streaming state
 */

import { create } from 'zustand';
import { streamChat } from '../lib/api';

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
  currentSkill: string | null;
  threadId: string | null;
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
  setCurrentSkill: (skill: string | null) => void;
  clearMessages: () => void;
  setThreadId: (threadId: string | null) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isStreaming: false,
  currentSkill: null,
  threadId: null,
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
        set({ threadId: newThreadId, currentSkill: skill });
      },
      // onError
      (error) => {
        set({ error, isStreaming: false });
      },
      // onDone
      () => {
        set({ isStreaming: false });
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

  setCurrentSkill: (skill: string | null) => {
    set({ currentSkill: skill });
  },

  clearMessages: () => {
    set({
      messages: [],
      currentSkill: null,
      threadId: null,
      error: null,
    });
  },

  setThreadId: (threadId: string | null) => {
    set({ threadId });
  },
}));

export default useChatStore;
