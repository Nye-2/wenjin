import { apiClient } from "@/lib/api/client";

export interface AdminCapabilitySummary {
  id: string;
  workspace_type: string;
  enabled: boolean;
  display_name: string;
  description: string;
  ui_meta: { icon: string; color: string; order: number };
}

export interface AdminCapabilityListResponse {
  groups: Record<string, AdminCapabilitySummary[]>;
  total: number;
}

export interface AdminCapabilityDetail {
  yaml: string;
  updated_at: string | null;
}

export interface ValidateResponse {
  valid: boolean;
  errors: string[];
}

export async function listAdminCapabilities(): Promise<AdminCapabilityListResponse> {
  const response = await apiClient.get("/admin/capabilities");
  return response.data;
}

export async function getAdminCapability(
  id: string,
  workspaceType: string
): Promise<AdminCapabilityDetail> {
  const response = await apiClient.get(`/admin/capabilities/${id}`, {
    params: { workspace_type: workspaceType },
  });
  return response.data;
}

export async function validateAdminCapability(
  yamlText: string
): Promise<ValidateResponse> {
  const response = await apiClient.post("/admin/capabilities/validate", {
    yaml: yamlText,
  });
  return response.data;
}

export async function createAdminCapability(
  yamlText: string
): Promise<AdminCapabilitySummary> {
  const response = await apiClient.post("/admin/capabilities", {
    yaml: yamlText,
  });
  return response.data;
}

export async function updateAdminCapability(
  id: string,
  workspaceType: string,
  yamlText: string
): Promise<AdminCapabilitySummary> {
  const response = await apiClient.put(
    `/admin/capabilities/${id}`,
    { yaml: yamlText },
    { params: { workspace_type: workspaceType } }
  );
  return response.data;
}

export async function deleteAdminCapability(
  id: string,
  workspaceType: string
): Promise<void> {
  await apiClient.delete(`/admin/capabilities/${id}`, {
    params: { workspace_type: workspaceType },
  });
}

export async function toggleAdminCapability(
  id: string,
  workspaceType: string
): Promise<AdminCapabilitySummary> {
  const response = await apiClient.post(
    `/admin/capabilities/${id}/toggle`,
    null,
    { params: { workspace_type: workspaceType } }
  );
  return response.data;
}

export async function importCapabilitiesFromSeed(): Promise<{
  loaded: Array<{ id: string; workspace_type: string }>;
}> {
  const response = await apiClient.post("/admin/capabilities/import-from-seed");
  return response.data;
}
