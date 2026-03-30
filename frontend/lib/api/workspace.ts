import { apiClient } from "@/lib/api/client";
import type {
  Artifact,
  DashboardData,
  ExecuteWorkspaceFeatureResponse,
  Literature,
  LiteratureListResponse,
  Paper,
  UploadPaperResponse,
  TaskStatus,
  Workspace,
  WorkspaceActivityResponse,
  WorkspaceCreate,
  WorkspaceChatSkill,
  WorkspaceFeature,
  WorkspaceSummaryData,
  WorkspaceTemplate,
} from "@/lib/api/types";

export async function listWorkspaces(): Promise<{ workspaces: Workspace[] }> {
  const response = await apiClient.get("/workspaces");
  return response.data;
}

export async function getWorkspace(id: string): Promise<Workspace> {
  const response = await apiClient.get(`/workspaces/${id}`);
  return response.data;
}

export async function createWorkspace(data: WorkspaceCreate): Promise<Workspace> {
  const response = await apiClient.post("/workspaces", data);
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

export async function listWorkspacePapers(
  workspaceId: string,
  readStatus?: string
): Promise<{ papers: Paper[]; count: number }> {
  const params = readStatus ? { read_status: readStatus } : {};
  const response = await apiClient.get(`/workspaces/${workspaceId}/papers`, {
    params,
  });
  return response.data;
}

export async function createPaper(data: {
  workspace_id: string;
  doi?: string;
  title: string;
  authors?: Array<{ name: string }>;
  year?: number;
  venue?: string;
  abstract?: string;
}): Promise<Paper> {
  const response = await apiClient.post("/papers", data);
  return response.data;
}

export async function uploadPaperFile(
  workspaceId: string,
  file: File
): Promise<UploadPaperResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("workspace_id", workspaceId);

  const response = await apiClient.post("/papers/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}

export async function searchPapers(
  query: string,
  workspaceId?: string,
  limit: number = 10
): Promise<{ query: string; count: number; papers: Paper[] }> {
  const response = await apiClient.post("/papers/search", {
    query,
    workspace_id: workspaceId,
    limit,
  });
  return response.data;
}

export async function listArtifacts(
  workspaceId: string,
  type?: string
): Promise<{ artifacts: Artifact[]; count: number }> {
  const params: Record<string, unknown> = {};
  if (type) {
    params.type = type;
  }
  const response = await apiClient.get(`/workspaces/${workspaceId}/artifacts`, {
    params,
  });
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
    {
      type: data.type,
      title: data.title,
      content: data.content,
      created_by_skill: data.created_by_skill,
      parent_artifact_id: data.parent_artifact_id,
    }
  );
  return response.data;
}

export async function getWorkspaceFeatures(
  workspaceId: string
): Promise<{ features: WorkspaceFeature[] }> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/features`);
  return response.data;
}

export async function getWorkspaceSkills(
  workspaceId: string
): Promise<{ skills: WorkspaceChatSkill[] }> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/skills`);
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

export async function cancelTask(taskId: string): Promise<void> {
  await apiClient.delete(`/tasks/${taskId}`);
}

export async function getWorkspaceDashboard(
  workspaceId: string
): Promise<DashboardData> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/dashboard`);
  return response.data;
}

export async function getWorkspaceSummary(
  workspaceId: string
): Promise<WorkspaceSummaryData> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/summary`);
  return response.data;
}

export async function getWorkspaceActivity(
  workspaceId: string,
  limit: number = 40
): Promise<WorkspaceActivityResponse> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/activity`, {
    params: { limit },
  });
  return response.data;
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
    is_core?: boolean;
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
  data: { source: string; artifact_ids?: string[] }
): Promise<{ imported: number }> {
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

export async function getWorkspaceTemplates(
  workspaceId: string
): Promise<{ templates: WorkspaceTemplate[] }> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/templates`);
  return response.data;
}

export async function getActiveTemplate(
  workspaceId: string
): Promise<WorkspaceTemplate | null> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/templates/active`);
  return response.data;
}

export async function uploadWorkspaceTemplate(
  workspaceId: string,
  file: File
): Promise<WorkspaceTemplate> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/templates/upload`,
    formData,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return response.data;
}

export async function deleteWorkspaceTemplate(
  workspaceId: string,
  templateId: string
): Promise<void> {
  await apiClient.delete(`/workspaces/${workspaceId}/templates/${templateId}`);
}
