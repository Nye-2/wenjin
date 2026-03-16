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
    if (typeof window !== 'undefined') {
      try {
        const authStorage = localStorage.getItem('auth-storage');
        if (authStorage) {
          const parsed = JSON.parse(authStorage);
          const token = parsed?.state?.accessToken;
          if (token) {
            config.headers.Authorization = `Bearer ${token}`;
          }
        }
      } catch (error) {
        console.error('Failed to parse auth token:', error);
      }
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
  type: 'sci' | 'thesis' | 'proposal' | 'software_copyright' | 'patent';
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

// ============ Feature Types ============

export interface FeatureStage {
  id: string;
  label: string;
}

export interface WorkspaceFeature {
  id: string;
  name: string;
  description: string;
  icon: string;  // icon name string, to be resolved by frontend
  agent: string;
  agentLabel: string;
  taskType?: string;
  panel?: string;  // which panel to show in right sidebar
  stages: FeatureStage[];
  color?: string;
}

export interface ExecuteWorkspaceFeatureResponse {
  task_id: string | null;
  status: string;
  feature_id: string;
  message: string;
  warning?: string;
  detail?: Record<string, unknown> | null;
}

export interface TaskStatus {
  task_id: string;
  task_type: string;
  status: string;
  progress: number;
  message?: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
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
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (typeof window !== 'undefined') {
    try {
      const authStorage = localStorage.getItem('auth-storage');
      if (authStorage) {
        const parsed = JSON.parse(authStorage);
        const token = parsed?.state?.accessToken;
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }
      }
    } catch (error) {
      console.error('Failed to parse auth token:', error);
    }
  }

  fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: 'POST',
    headers,
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

// ============ Features API ============

export async function getWorkspaceFeatures(
  workspaceId: string
): Promise<{ features: WorkspaceFeature[] }> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/features`);
  return response.data;
}

export async function executeWorkspaceFeature(
  workspaceId: string,
  featureId: string,
  params: Record<string, unknown> = {},
  threadId?: string
): Promise<ExecuteWorkspaceFeatureResponse> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/features/${featureId}/execute`,
    {
      params,
      thread_id: threadId,
    }
  );
  return response.data;
}

export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  const response = await apiClient.get(`/tasks/${taskId}`);
  return response.data;
}

// ============ Dashboard API ============

export interface ModuleStatus {
  id: string;
  status: 'not_started' | 'in_progress' | 'completed' | 'failed';
  summary: Record<string, unknown>;
}

export interface DashboardData {
  modules: ModuleStatus[];
  recent_artifacts: Array<{
    id: string;
    type: string;
    title: string | null;
    created_at: string;
  }>;
}

export async function getWorkspaceDashboard(
  workspaceId: string
): Promise<DashboardData> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/dashboard`);
  return response.data;
}

// ============ User/Admin Dashboard API ============

export interface CreditTransactionItem {
  id: string;
  user_id?: string;
  user_email?: string;
  user_name?: string | null;
  type: string;
  amount: number;
  balance_after: number;
  description?: string | null;
  feature_id?: string | null;
  created_at: string;
}

export interface UserDashboardData {
  profile: {
    id: string;
    email: string;
    name: string | null;
    role: 'user' | 'admin';
    is_active: boolean;
    created_at: string | null;
    last_login: string | null;
  };
  credits: {
    balance: number;
    total_earned: number;
    total_spent: number;
    costs: Record<string, number | Record<string, number>>;
  };
  workspaces: {
    total: number;
    by_type: Record<string, number>;
    created_last_7d: number;
  };
  tasks: {
    total: number;
    success: number;
    running: number;
    failed: number;
    pending: number;
    cancelled: number;
    completion_rate: number;
  };
  recent_credit_transactions: CreditTransactionItem[];
  recent_tasks: Array<{
    id: string;
    task_type: string;
    status: string;
    progress: number;
    message?: string | null;
    created_at: string | null;
    completed_at: string | null;
  }>;
  updated_at: string;
}

export interface AdminDashboardData {
  summary: {
    users: {
      total: number;
      active: number;
      admins: number;
    };
    workspaces: {
      total: number;
      by_type: Record<string, number>;
    };
    tasks: {
      total: number;
      running: number;
      failed_last_24h: number;
    };
    artifacts: {
      total: number;
    };
    credits: {
      total_issued: number;
      total_spent: number;
      in_circulation: number;
      total_transactions: number;
    };
  };
  recent_users: AdminUserItem[];
  top_spenders: Array<{
    id: string;
    email: string;
    name: string | null;
    total_spent: number;
    balance: number;
  }>;
  recent_credit_transactions: CreditTransactionItem[];
  recent_admin_logs: AdminLogItem[];
  updated_at: string;
}

export interface AdminUserItem {
  id: string;
  email: string;
  name: string | null;
  role: 'user' | 'admin';
  is_active: boolean;
  credits: number;
  total_credits_earned: number;
  total_credits_spent: number;
  created_at: string | null;
  last_login: string | null;
}

export interface AdminLogItem {
  id: string;
  admin_id?: string;
  action: string;
  target_type: string;
  target_user_id: string | null;
  details: Record<string, unknown>;
  ip_address?: string | null;
  created_at: string | null;
  admin?: {
    id: string;
    email: string;
    name: string | null;
  };
  target_user?: {
    id: string;
    email: string;
    name: string | null;
  } | null;
}

export async function getMyDashboard(): Promise<UserDashboardData> {
  const response = await apiClient.get('/dashboard/me');
  return response.data;
}

export async function getMyCreditHistory(params?: {
  page?: number;
  page_size?: number;
  transaction_type?: string;
}): Promise<{
  transactions: CreditTransactionItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}> {
  const response = await apiClient.get('/dashboard/me/credits/history', { params });
  return response.data;
}

export async function getWorkflowCreditCosts(): Promise<{
  costs: Record<string, number | Record<string, number>>;
}> {
  const response = await apiClient.get('/dashboard/me/credits/costs');
  return response.data;
}

export async function getAdminDashboard(): Promise<AdminDashboardData> {
  const response = await apiClient.get('/dashboard/admin');
  return response.data;
}

export async function listAdminUsers(params?: {
  page?: number;
  page_size?: number;
  keyword?: string;
  is_active?: boolean;
  role?: 'user' | 'admin';
}): Promise<{
  users: AdminUserItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}> {
  const response = await apiClient.get('/dashboard/admin/users', { params });
  return response.data;
}

export async function updateAdminUserStatus(
  userId: string,
  isActive: boolean
): Promise<{ success: boolean; user: AdminUserItem }> {
  const response = await apiClient.post(`/dashboard/admin/users/${userId}/status`, {
    is_active: isActive,
  });
  return response.data;
}

export async function updateAdminUserRole(
  userId: string,
  role: 'user' | 'admin'
): Promise<{ success: boolean; user: AdminUserItem }> {
  const response = await apiClient.post(`/dashboard/admin/users/${userId}/role`, {
    role,
  });
  return response.data;
}

export async function adminGrantCredits(data: {
  user_id: string;
  amount: number;
  description?: string;
}): Promise<{
  success: boolean;
  transaction: {
    id: string;
    amount: number;
    balance_after: number;
  };
}> {
  const response = await apiClient.post('/dashboard/admin/credits/grant', data);
  return response.data;
}

export async function adminDeductCredits(data: {
  user_id: string;
  amount: number;
  description?: string;
}): Promise<{
  success: boolean;
  transaction: {
    id: string;
    amount: number;
    balance_after: number;
  };
}> {
  const response = await apiClient.post('/dashboard/admin/credits/deduct', data);
  return response.data;
}

export async function getAdminCreditHistory(params?: {
  page?: number;
  page_size?: number;
  user_id?: string;
  transaction_type?: string;
}): Promise<{
  transactions: CreditTransactionItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}> {
  const response = await apiClient.get('/dashboard/admin/credits/history', { params });
  return response.data;
}

export async function getAdminLogs(params?: {
  page?: number;
  page_size?: number;
  action?: string;
  target_user_id?: string;
}): Promise<{
  logs: AdminLogItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}> {
  const response = await apiClient.get('/dashboard/admin/logs', { params });
  return response.data;
}

// ============ Literature API ============

export interface Literature {
  id: string;
  title: string;
  authors: string[];
  year: number | null;
  citations: number | null;
  venue: string | null;
  quartile: string | null;
  abstract: string | null;
  doi: string | null;
  source: string;
  is_core: boolean;
  created_at: string;
}

export interface LiteratureListResponse {
  items: Literature[];
  total: number;
  core_count: number;
}

export async function listLiterature(
  workspaceId: string,
  params?: { source?: string; is_core?: boolean }
): Promise<LiteratureListResponse> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/literature`, {
    params,
  });
  return response.data;
}

export async function createLiterature(
  workspaceId: string,
  data: {
    title: string;
    authors: string[];
    year?: number;
    doi?: string;
    venue?: string;
    quartile?: string;
    abstract?: string;
    citations?: number;
    source?: string;
  }
): Promise<Literature> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/literature`,
    data
  );
  return response.data;
}

export async function importLiterature(
  workspaceId: string,
  data: { source: string; paper_ids: string[] }
): Promise<{ imported: number; items: Literature[] }> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/literature/import`,
    data
  );
  return response.data;
}

export async function updateLiterature(
  workspaceId: string,
  litId: string,
  data: { is_core?: boolean; title?: string; authors?: string[] }
): Promise<Literature> {
  const response = await apiClient.patch(
    `/workspaces/${workspaceId}/literature/${litId}`,
    data
  );
  return response.data;
}

export async function deleteLiterature(
  workspaceId: string,
  litId: string
): Promise<void> {
  await apiClient.delete(`/workspaces/${workspaceId}/literature/${litId}`);
}

export async function getLiteratureCount(
  workspaceId: string
): Promise<{ total: number; core: number }> {
  const response = await apiClient.get(
    `/workspaces/${workspaceId}/literature/count`
  );
  return response.data;
}

export default apiClient;
