import { apiClient } from "@/lib/api/client";
import type {
  ChatAttachment,
  ChatUploadKind,
  Thread,
  ThreadAgentStatus,
} from "@/lib/api/types";

export async function ensureWorkspaceChatThread(
  workspaceId: string,
  data: {
    model?: string;
    skill?: string | null;
  } = {}
): Promise<Thread> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/chat-thread`,
    data
  );
  return response.data;
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
