import { apiClient } from "@/lib/api/client";
import type {
  ThreadAttachment,
  ThreadUploadKind,
  Thread,
} from "@/lib/api/types";

export async function ensureWorkspaceThread(
  workspaceId: string,
  data: {
    model?: string;
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
