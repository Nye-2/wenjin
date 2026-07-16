import { apiClient } from "@/lib/api/client";
import type {
  Artifact,
  DashboardData,
  ReferenceBibtexResponse,
  ReferenceBibtexValidationResponse,
  ReferenceCountResponse,
  ReferenceDetailResponse,
  ReferenceImportResponse,
  ReferenceListResponse,
  UploadReferenceResponse,
  WorkspaceReference,
  Workspace,
  WorkspaceActivityResponse,
  WorkspaceCreate,
  WorkspacePrismFileContent,
  WorkspacePrismFileWrite,
  WorkspacePrismEnsureResponse,
  WorkspacePrismSurfaceResponse,
  WorkspaceSummaryData,
  WorkspaceSettings,
  WorkspaceSettingsUpdate,
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

export async function getWorkspaceSettings(
  workspaceId: string,
): Promise<WorkspaceSettings> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/settings`);
  return response.data;
}

export async function updateWorkspaceSettings(
  workspaceId: string,
  settings: WorkspaceSettingsUpdate,
): Promise<WorkspaceSettings> {
  const response = await apiClient.put(
    `/workspaces/${workspaceId}/settings`,
    settings,
  );
  return response.data;
}

export async function ensureWorkspacePrismProject(
  workspaceId: string
): Promise<WorkspacePrismEnsureResponse> {
  const response = await apiClient.post(`/workspaces/${workspaceId}/prism/ensure`);
  return response.data;
}

export async function getWorkspacePrismSurface(
  workspaceId: string
): Promise<WorkspacePrismSurfaceResponse> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/prism`);
  return response.data;
}

export async function createWorkspacePrismFile(
  workspaceId: string,
  data: {
    path: string;
    content_inline?: string;
    file_role?: string;
    mime_type?: string | null;
  },
): Promise<WorkspacePrismFileWrite> {
  const response = await apiClient.post(`/workspaces/${workspaceId}/prism/files`, {
    path: data.path,
    content_inline: data.content_inline ?? "",
    file_role: data.file_role ?? "manual",
    mime_type: data.mime_type ?? undefined,
  });
  return response.data;
}

export async function getWorkspacePrismFile(
  workspaceId: string,
  fileId: string,
): Promise<WorkspacePrismFileContent> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/prism/files/${fileId}`);
  return response.data;
}

export async function saveWorkspacePrismFile(
  workspaceId: string,
  fileId: string,
  data: {
    content_inline: string;
    expected_current_hash?: string | null;
  },
): Promise<WorkspacePrismFileWrite> {
  const response = await apiClient.put(`/workspaces/${workspaceId}/prism/files/${fileId}`, data);
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

export async function listWorkspaceReferences(
  workspaceId: string,
  params?: {
    library_status?: string;
    source_type?: string;
    query?: string;
    offset?: number;
    limit?: number;
  }
): Promise<ReferenceListResponse> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/references`, {
    params,
  });
  return response.data;
}

export async function createManualReference(
  workspaceId: string,
  data: Partial<WorkspaceReference> & { title: string }
): Promise<{ reference: WorkspaceReference; created: boolean }> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/manual`,
    data
  );
  return response.data;
}

export async function uploadReferenceFile(
  workspaceId: string,
  file: File
): Promise<UploadReferenceResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/upload`,
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );
  return response.data;
}

export async function importLiteratureSearchReferences(
  workspaceId: string,
  data: { query: string; discipline?: string | null; limit?: number }
): Promise<ReferenceImportResponse> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/import/literature-search`,
    data
  );
  return response.data;
}

export async function importDeepSearchArtifactReferences(
  workspaceId: string,
  data: { artifact_ids: string[] }
): Promise<ReferenceImportResponse> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/import/deep-search-artifact`,
    data
  );
  return response.data;
}

export async function importBibtexReferences(
  workspaceId: string,
  content: string
): Promise<ReferenceImportResponse> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/import/bibtex`,
    { content }
  );
  return response.data;
}

export async function updateReference(
  workspaceId: string,
  referenceId: string,
  data: Partial<WorkspaceReference>
): Promise<WorkspaceReference> {
  const response = await apiClient.patch(
    `/workspaces/${workspaceId}/references/${referenceId}`,
    data
  );
  return response.data;
}

export async function deleteReference(
  workspaceId: string,
  referenceId: string
): Promise<void> {
  await apiClient.delete(`/workspaces/${workspaceId}/references/${referenceId}`);
}

export async function getReferenceCount(
  workspaceId: string
): Promise<ReferenceCountResponse> {
  const response = await apiClient.get(
    `/workspaces/${workspaceId}/references/count`
  );
  return response.data;
}

export async function getReferenceBibtex(
  workspaceId: string,
  scope: string = "included_and_core"
): Promise<ReferenceBibtexResponse> {
  const response = await apiClient.get(
    `/workspaces/${workspaceId}/references/bibtex`,
    { params: { scope } }
  );
  return response.data;
}

export async function syncReferenceBibtexToPrism(
  workspaceId: string,
  scope: string = "included_and_core"
): Promise<ReferenceBibtexResponse> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/bibtex/sync-prism`,
    { scope }
  );
  return response.data;
}

export async function searchReferenceTextUnits(
  workspaceId: string,
  data: { query: string; reference_ids?: string[]; limit?: number }
): Promise<{ items: Array<Record<string, unknown>>; count: number }> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/search-text-units`,
    data
  );
  return response.data;
}

export async function buildReferenceEvidencePack(
  workspaceId: string,
  data: { query?: string | null; reference_ids?: string[]; max_units?: number }
): Promise<Record<string, unknown>> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/evidence-pack`,
    data
  );
  return response.data;
}

export async function getReferenceOutline(
  workspaceId: string,
  referenceId: string
): Promise<{ items: Array<Record<string, unknown>>; count: number }> {
  const response = await apiClient.get(
    `/workspaces/${workspaceId}/references/${referenceId}/outline`
  );
  return response.data;
}

export async function readReferenceOutlineNode(
  workspaceId: string,
  referenceId: string,
  nodeId: string
): Promise<Record<string, unknown>> {
  const response = await apiClient.get(
    `/workspaces/${workspaceId}/references/${referenceId}/outline/${nodeId}/content`
  );
  return response.data;
}

export async function markReferenceIncluded(
  workspaceId: string,
  referenceId: string
): Promise<WorkspaceReference> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/${referenceId}/mark-included`
  );
  return response.data;
}

export async function markReferenceCore(
  workspaceId: string,
  referenceId: string
): Promise<WorkspaceReference> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/${referenceId}/mark-core`
  );
  return response.data;
}

export async function excludeReference(
  workspaceId: string,
  referenceId: string
): Promise<WorkspaceReference> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/${referenceId}/exclude`
  );
  return response.data;
}

export async function markReferenceRead(
  workspaceId: string,
  referenceId: string
): Promise<WorkspaceReference> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/${referenceId}/mark-read`
  );
  return response.data;
}

export async function getWorkspaceReferenceLibraryOutline(
  workspaceId: string
): Promise<{ items: Array<Record<string, unknown>>; count: number }> {
  const response = await apiClient.get(
    `/workspaces/${workspaceId}/references/outline`
  );
  return response.data;
}

export async function getReferenceDetail(
  workspaceId: string,
  referenceId: string
): Promise<ReferenceDetailResponse> {
  const response = await apiClient.get(
    `/workspaces/${workspaceId}/references/${referenceId}`
  );
  return response.data;
}

export async function uploadReferencePdf(
  workspaceId: string,
  file: File
): Promise<UploadReferenceResponse> {
  return uploadReferenceFile(workspaceId, file);
}

export async function uploadReferenceBibtexFile(
  workspaceId: string,
  file: File
): Promise<ReferenceImportResponse> {
  const content = await file.text();
  return importBibtexReferences(workspaceId, content);
}

export async function listReferenceCandidatesByLiteratureSearch(
  workspaceId: string,
  query: string,
  limit: number = 10
): Promise<ReferenceImportResponse> {
  return importLiteratureSearchReferences(workspaceId, { query, limit });
}

export async function syncReferencesToPrism(
  workspaceId: string
): Promise<ReferenceBibtexResponse> {
  return syncReferenceBibtexToPrism(workspaceId);
}

export async function validateReferenceBibtex(
  workspaceId: string,
  latexContent?: string
): Promise<ReferenceBibtexValidationResponse> {
  const response = await apiClient.post(
    `/workspaces/${workspaceId}/references/bibtex/validate`,
    latexContent ? { latex_content: latexContent } : undefined
  );
  return response.data;
}

export async function getReferencePages(
  workspaceId: string,
  referenceId: string,
  pageStart: number,
  pageEnd: number
): Promise<{ items: Array<Record<string, unknown>>; count: number }> {
  const response = await apiClient.get(
    `/workspaces/${workspaceId}/references/${referenceId}/pages`,
    {
      params: {
        page_start: pageStart,
        page_end: pageEnd,
      },
    }
  );
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

export async function activateWorkspaceTemplate(
  workspaceId: string,
  templateId: string
): Promise<WorkspaceTemplate> {
  const response = await apiClient.put(
    `/workspaces/${workspaceId}/templates/${templateId}/activate`
  );
  return response.data;
}

export async function deleteWorkspaceTemplate(
  workspaceId: string,
  templateId: string
): Promise<void> {
  await apiClient.delete(`/workspaces/${workspaceId}/templates/${templateId}`);
}
