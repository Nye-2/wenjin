import { apiClient } from "@/lib/api/client";
import type {
  ChatMessage,
  ChatRequest,
  Thread,
  ThreadAgentStatus,
  ThreadSummary,
} from "@/lib/api/types";

export async function createThread(data: {
  workspace_id?: string;
  title?: string;
  model?: string;
  skill?: string | null;
}): Promise<Thread> {
  const response = await apiClient.post("/threads", data);
  return response.data;
}

export async function getThread(threadId: string): Promise<Thread> {
  const response = await apiClient.get(`/threads/${threadId}`);
  return response.data;
}

export async function listThreads(
  workspaceId?: string,
  limit: number = 20
): Promise<{ threads: ThreadSummary[]; count: number }> {
  const params: Record<string, unknown> = { limit };
  if (workspaceId) {
    params.workspace_id = workspaceId;
  }
  const response = await apiClient.get("/threads", { params });
  return response.data;
}

export async function deleteThread(threadId: string): Promise<void> {
  await apiClient.delete(`/threads/${threadId}`);
}

export async function getThreadAgentStatus(
  threadId: string
): Promise<ThreadAgentStatus> {
  const response = await apiClient.get(`/threads/${threadId}/agent-status`);
  return response.data;
}

export async function sendMessage(data: ChatRequest): Promise<{
  thread_id: string;
  message: ChatMessage;
  workspace_id?: string;
}> {
  const response = await apiClient.post("/chat", data);
  return response.data;
}
