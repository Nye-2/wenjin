import { apiClient } from "@/lib/api/client";
import type {
  ThreadAttachment,
  ThreadUploadKind,
  PlatformThreadHistoryEntry,
  PlatformThreadState,
  PlatformThreadSummary,
  Thread,
} from "@/lib/api/types";

export async function ensureWorkspaceThread(
  workspaceId: string,
  data: {
    model?: string;
    skill?: string | null;
  } = {}
): Promise<Thread> {
  const response = await apiClient.post(
    `/workspaces/${encodeURIComponent(workspaceId)}/thread`,
    data
  );
  return response.data;
}

export async function uploadThreadFiles(options: {
  threadId: string;
  kind: ThreadUploadKind;
  workspaceId?: string;
  files: File[];
}): Promise<{ success: boolean; files: ThreadAttachment[]; message: string }> {
  const formData = new FormData();
  formData.append("kind", options.kind);
  if (options.workspaceId) {
    formData.append("workspace_id", options.workspaceId);
  }
  for (const file of options.files) {
    formData.append("files", file);
  }

  const response = await apiClient.post(
    `/threads/${encodeURIComponent(options.threadId)}/uploads`,
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );
  return response.data;
}

export async function searchThreads(options: {
  metadata?: Record<string, unknown>;
  status?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<PlatformThreadSummary[]> {
  const response = await apiClient.post("/threads/search", {
    metadata: options.metadata ?? {},
    status: options.status,
    limit: options.limit ?? 100,
    offset: options.offset ?? 0,
  });
  return response.data;
}

export async function getThreadState(
  threadId: string
): Promise<PlatformThreadState> {
  const response = await apiClient.get(
    `/threads/${encodeURIComponent(threadId)}/state`
  );
  return response.data;
}

export async function getThreadHistory(
  threadId: string,
  options: {
    limit?: number;
    before?: string;
  } = {}
): Promise<PlatformThreadHistoryEntry[]> {
  const response = await apiClient.post(
    `/threads/${encodeURIComponent(threadId)}/history`,
    {
      limit: options.limit ?? 10,
      before: options.before,
    }
  );
  return response.data;
}
