import { apiClient } from "@/lib/api/client";
import type {
  ChatAttachment,
  ChatUploadKind,
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

export async function uploadThreadFiles(options: {
  threadId: string;
  kind: ChatUploadKind;
  workspaceId?: string;
  files: File[];
}): Promise<{ success: boolean; files: ChatAttachment[]; message: string }> {
  const formData = new FormData();
  formData.append("kind", options.kind);
  if (options.workspaceId) {
    formData.append("workspace_id", options.workspaceId);
  }
  for (const file of options.files) {
    formData.append("files", file);
  }

  const response = await apiClient.post(
    `/threads/${options.threadId}/uploads`,
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );
  return response.data;
}

export async function getThreadAgentStatus(
  threadId: string
): Promise<ThreadAgentStatus> {
  const response = await apiClient.get(`/threads/${threadId}/agent-status`);
  return response.data;
}
