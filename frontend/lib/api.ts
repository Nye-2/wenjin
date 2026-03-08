/**
 * API Client for AcademiaGPT Backend
 */

import axios, { AxiosInstance, AxiosError } from 'axios';

// API Configuration
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

// Create axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// Request interceptor
apiClient.interceptors.request.use(
  (config) => {
    // Add auth token if available
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    console.error('API Error:', error.response?.data || error.message);
    return Promise.reject(error);
  }
);

// ============ Types ============

export interface Workspace {
  id: string;
  user_id: string;
  name: string;
  type: 'sci' | 'thesis' | 'proposal' | 'grant';
  discipline?: string;
  description?: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceCreate {
  name: string;
  type: string;
  discipline?: string;
  description?: string;
  config?: Record<string, unknown>;
}

export interface Paper {
  id: string;
  doi?: string;
  title: string;
  authors: Array<{ name: string; id?: string }>;
  year?: number;
  venue?: string;
  abstract?: string;
  source: string;
  citation_count?: number;
  reference_count?: number;
}

export interface Artifact {
  id: string;
  workspace_id: string;
  type: string;
  title?: string;
  content: Record<string, unknown>;
  created_by_skill?: string;
  parent_artifact_id?: string;
  version: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
}

export interface Thread {
  id: string;
  workspace_id?: string;
  title?: string;
  model: string;
  messages: ChatMessage[];
  created_at: string;
  updated_at: string;
}

export interface ChatRequest {
  message: string;
  workspace_id?: string;
  thread_id?: string;
  model?: string;
  thinking_enabled?: boolean;
  stream?: boolean;
}

export interface Model {
  name: string;
  display_name: string;
  provider: string;
  max_tokens: number;
  supports_thinking: boolean;
  supports_vision: boolean;
}

// ============ API Functions ============

// Health check
export async function healthCheck(): Promise<{ status: string; version: string }> {
  const response = await apiClient.get('/health');
  return response.data;
}

// ============ Workspace API ============

export async function listWorkspaces(): Promise<{ workspaces: Workspace[] }> {
  const response = await apiClient.get('/workspaces');
  return response.data;
}

export async function getWorkspace(id: string): Promise<Workspace> {
  const response = await apiClient.get(`/workspaces/${id}`);
  return response.data;
}

export async function createWorkspace(data: WorkspaceCreate): Promise<Workspace> {
  const response = await apiClient.post('/workspaces', data);
  return response.data;
}

export async function updateWorkspace(
  id: string,
  data: Partial<WorkspaceCreate>
): Promise<Workspace> {
  const response = await apiClient.put(`/workspaces/${id}`, data);
  return response.data;
}

export async function deleteWorkspace(id: string): Promise<void> {
  await apiClient.delete(`/workspaces/${id}`);
}

// ============ Paper API ============

export async function listWorkspacePapers(
  workspaceId: string,
  readStatus?: string
): Promise<{ papers: Paper[]; count: number }> {
  const params = readStatus ? { read_status: readStatus } : {};
  const response = await apiClient.get(`/workspaces/${workspaceId}/papers`, { params });
  return response.data;
}

export async function createPaper(data: {
  doi?: string;
  title: string;
  authors?: Array<{ name: string }>;
  year?: number;
  venue?: string;
  abstract?: string;
}): Promise<Paper> {
  const response = await apiClient.post('/papers', data);
  return response.data;
}

export async function searchPapers(
  query: string,
  limit: number = 10
): Promise<{ result: string }> {
  const response = await apiClient.get('/papers/search', {
    params: { query, limit },
  });
  return response.data;
}

// ============ Artifact API ============

export async function listArtifacts(
  workspaceId: string,
  type?: string
): Promise<{ artifacts: Artifact[]; count: number }> {
  const params = type ? { artifact_type: type } : {};
  const response = await apiClient.get(`/workspaces/${workspaceId}/artifacts`, { params });
  return response.data;
}

export async function createArtifact(data: {
  workspace_id: string;
  type: string;
  title?: string;
  content: Record<string, unknown>;
  created_by_skill?: string;
  parent_artifact_id?: string;
}): Promise<Artifact> {
  const response = await apiClient.post(
    `/workspaces/${data.workspace_id}/artifacts`,
    data
  );
  return response.data;
}

// ============ Chat API ============

export async function createThread(data: {
  workspace_id?: string;
  title?: string;
  model?: string;
}): Promise<Thread> {
  const response = await apiClient.post('/threads', data);
  return response.data;
}

export async function getThread(threadId: string): Promise<Thread> {
  const response = await apiClient.get(`/threads/${threadId}`);
  return response.data;
}

export async function listThreads(
  workspaceId?: string,
  limit: number = 20
): Promise<{ threads: Thread[]; count: number }> {
  const params: Record<string, unknown> = { limit };
  if (workspaceId) params.workspace_id = workspaceId;
  const response = await apiClient.get('/threads', { params });
  return response.data;
}

export async function deleteThread(threadId: string): Promise<void> {
  await apiClient.delete(`/threads/${threadId}`);
}

export async function sendMessage(data: ChatRequest): Promise<{
  thread_id: string;
  message: ChatMessage;
  workspace_id?: string;
}> {
  const response = await apiClient.post('/chat', data);
  return response.data;
}

// Streaming chat
export function streamChat(
  data: ChatRequest,
  onMessage: (content: string) => void,
  onThreadId?: (threadId: string) => void,
  onError?: (error: string) => void,
  onDone?: () => void
): () => void {
  const controller = new AbortController();

  fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ...data, stream: true }),
    signal: controller.signal,
  })
    .then(async (response) => {
      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader available');

      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const json = JSON.parse(line.slice(6));

              switch (json.type) {
                case 'thread_id':
                  onThreadId?.(json.thread_id);
                  break;
                case 'content':
                  onMessage(json.content);
                  break;
                case 'error':
                  onError?.(json.error);
                  break;
                case 'done':
                  onDone?.();
                  break;
              }
            } catch {
              // Ignore parse errors
            }
          }
        }
      }
    })
    .catch((error) => {
      if (error.name !== 'AbortError') {
        onError?.(error.message);
      }
    });

  return () => controller.abort();
}

// ============ Models API ============

export async function listModels(): Promise<{ models: Model[] }> {
  const response = await apiClient.get('/models');
  return response.data;
}

export default apiClient;
