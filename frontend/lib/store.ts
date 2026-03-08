/**
 * Zustand Store for AcademiaGPT
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  Workspace,
  Paper,
  Artifact,
  Thread,
  ChatMessage,
  Model,
  listWorkspaces,
  createWorkspace,
  deleteWorkspace,
  listWorkspacePapers,
  listArtifacts,
  sendMessage,
  streamChat,
  listModels,
  listThreads,
  createThread,
  getThread,
} from './api';

// ============ Workspace Store ============

interface WorkspaceState {
  workspaces: Workspace[];
  currentWorkspace: Workspace | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchWorkspaces: () => Promise<void>;
  setCurrentWorkspace: (workspace: Workspace | null) => void;
  addWorkspace: (data: { name: string; type: string; discipline?: string }) => Promise<Workspace>;
  removeWorkspace: (id: string) => Promise<void>;
  clearError: () => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  workspaces: [],
  currentWorkspace: null,
  isLoading: false,
  error: null,

  fetchWorkspaces: async () => {
    set({ isLoading: true, error: null });
    try {
      const response = await listWorkspaces();
      set({ workspaces: response.workspaces, isLoading: false });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  setCurrentWorkspace: (workspace) => {
    set({ currentWorkspace: workspace });
  },

  addWorkspace: async (data) => {
    set({ isLoading: true, error: null });
    try {
      const workspace = await createWorkspace(data);
      set((state) => ({
        workspaces: [...state.workspaces, workspace],
        isLoading: false,
      }));
      return workspace;
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
      throw error;
    }
  },

  removeWorkspace: async (id) => {
    set({ isLoading: true, error: null });
    try {
      await deleteWorkspace(id);
      set((state) => ({
        workspaces: state.workspaces.filter((w) => w.id !== id),
        currentWorkspace:
          state.currentWorkspace?.id === id ? null : state.currentWorkspace,
        isLoading: false,
      }));
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  clearError: () => set({ error: null }),
}));

// ============ Paper Store ============

interface PaperState {
  papers: Paper[];
  isLoading: boolean;
  error: string | null;

  fetchPapers: (workspaceId: string) => Promise<void>;
  clearPapers: () => void;
}

export const usePaperStore = create<PaperState>((set) => ({
  papers: [],
  isLoading: false,
  error: null,

  fetchPapers: async (workspaceId) => {
    set({ isLoading: true, error: null });
    try {
      const response = await listWorkspacePapers(workspaceId);
      set({ papers: response.papers, isLoading: false });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  clearPapers: () => set({ papers: [] }),
}));

// ============ Artifact Store ============

interface ArtifactState {
  artifacts: Artifact[];
  isLoading: boolean;
  error: string | null;

  fetchArtifacts: (workspaceId: string, type?: string) => Promise<void>;
  clearArtifacts: () => void;
}

export const useArtifactStore = create<ArtifactState>((set) => ({
  artifacts: [],
  isLoading: false,
  error: null,

  fetchArtifacts: async (workspaceId, type) => {
    set({ isLoading: true, error: null });
    try {
      const response = await listArtifacts(workspaceId, type);
      set({ artifacts: response.artifacts, isLoading: false });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  clearArtifacts: () => set({ artifacts: [] }),
}));

// ============ Chat Store ============

interface ChatState {
  threads: Thread[];
  currentThread: Thread | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  isTyping: boolean;
  currentModel: string;
  thinkingEnabled: boolean;
  error: string | null;

  // Actions
  fetchThreads: (workspaceId?: string) => Promise<void>;
  setCurrentThread: (thread: Thread | null) => void;
  loadThread: (threadId: string) => Promise<void>;
  startNewThread: (workspaceId?: string) => Promise<void>;
  sendMessage: (
    content: string,
    workspaceId?: string,
    onComplete?: () => void
  ) => Promise<void>;
  setModel: (model: string) => void;
  setThinkingEnabled: (enabled: boolean) => void;
  clearMessages: () => void;
  addMessage: (message: ChatMessage) => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      threads: [],
      currentThread: null,
      messages: [],
      isStreaming: false,
      isTyping: false,
      currentModel: 'gpt-4o',
      thinkingEnabled: false,
      error: null,

      fetchThreads: async (workspaceId) => {
        try {
          const response = await listThreads(workspaceId);
          set({ threads: response.threads });
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      setCurrentThread: (thread) => {
        set({
          currentThread: thread,
          messages: thread?.messages || [],
        });
      },

      loadThread: async (threadId) => {
        try {
          const thread = await getThread(threadId);
          set({
            currentThread: thread,
            messages: thread.messages,
          });
        } catch (error) {
          set({ error: (error as Error).message });
        }
      },

      startNewThread: async (workspaceId) => {
        set({
          currentThread: null,
          messages: [],
        });
      },

      sendMessage: async (content, workspaceId, onComplete) => {
        const { currentThread, currentModel, thinkingEnabled } = get();

        // Add user message immediately
        const userMessage: ChatMessage = {
          role: 'user',
          content,
          timestamp: new Date().toISOString(),
        };
        set((state) => ({
          messages: [...state.messages, userMessage],
          isStreaming: true,
          isTyping: true,
        }));

        // Prepare placeholder for assistant message
        let assistantContent = '';
        const assistantMessage: ChatMessage = {
          role: 'assistant',
          content: '',
          timestamp: new Date().toISOString(),
        };
        set((state) => ({
          messages: [...state.messages, assistantMessage],
        }));

        // Stream response
        const abort = streamChat(
          {
            message: content,
            workspace_id: workspaceId,
            thread_id: currentThread?.id,
            model: currentModel,
            thinking_enabled: thinkingEnabled,
          },
          // onMessage
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
              return { messages, isTyping: true };
            });
          },
          // onThreadId
          (threadId) => {
            set({
              currentThread: {
                id: threadId,
                model: currentModel,
                messages: [],
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              },
            });
          },
          // onError
          (error) => {
            set({ error, isStreaming: false, isTyping: false });
          },
          // onDone
          () => {
            set({ isStreaming: false, isTyping: false });
            onComplete?.();
          }
        );

        // Store abort function for potential cleanup
        // In a real app, you might want to store this in state
      },

      setModel: (model) => set({ currentModel: model }),
      setThinkingEnabled: (enabled) => set({ thinkingEnabled: enabled }),
      clearMessages: () => set({ messages: [], currentThread: null }),
      addMessage: (message) =>
        set((state) => ({ messages: [...state.messages, message] })),
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        currentModel: state.currentModel,
        thinkingEnabled: state.thinkingEnabled,
      }),
    }
  )
);

// ============ Model Store ============

interface ModelState {
  models: Model[];
  isLoading: boolean;
  error: string | null;

  fetchModels: () => Promise<void>;
}

export const useModelStore = create<ModelState>((set) => ({
  models: [],
  isLoading: false,
  error: null,

  fetchModels: async () => {
    set({ isLoading: true });
    try {
      const response = await listModels();
      set({ models: response.models, isLoading: false });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },
}));

// ============ UI Store ============

interface UIState {
  sidebarOpen: boolean;
  theme: 'light' | 'dark' | 'system';

  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      theme: 'system',

      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      setTheme: (theme) => set({ theme }),
    }),
    {
      name: 'ui-storage',
    }
  )
);
