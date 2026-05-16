import { apiClient } from "@/lib/api/client";

export interface AdminSkillSummary {
  id: string;
  enabled: boolean;
  display_name: string;
  description: string;
  subagent_type: string;
}

export interface AdminSkillListResponse {
  items: AdminSkillSummary[];
  total: number;
}

export interface AdminSkillDetail {
  yaml: string;
  updated_at: string | null;
}

export interface ValidateResponse {
  valid: boolean;
  errors: string[];
}

export async function listAdminSkills(): Promise<AdminSkillListResponse> {
  const response = await apiClient.get("/admin/skills");
  return response.data;
}

export async function getAdminSkill(id: string): Promise<AdminSkillDetail> {
  const response = await apiClient.get(`/admin/skills/${id}`);
  return response.data;
}

export async function validateAdminSkill(
  yamlText: string
): Promise<ValidateResponse> {
  const response = await apiClient.post("/admin/skills/validate", {
    yaml: yamlText,
  });
  return response.data;
}

export async function createAdminSkill(
  yamlText: string
): Promise<AdminSkillSummary> {
  const response = await apiClient.post("/admin/skills", { yaml: yamlText });
  return response.data;
}

export async function updateAdminSkill(
  id: string,
  yamlText: string
): Promise<AdminSkillSummary> {
  const response = await apiClient.put(`/admin/skills/${id}`, {
    yaml: yamlText,
  });
  return response.data;
}

export async function deleteAdminSkill(id: string): Promise<void> {
  await apiClient.delete(`/admin/skills/${id}`);
}

export async function toggleAdminSkill(
  id: string
): Promise<AdminSkillSummary> {
  const response = await apiClient.post(`/admin/skills/${id}/toggle`);
  return response.data;
}

export async function importSkillsFromSeed(): Promise<{
  loaded: Array<{ id: string }>;
}> {
  const response = await apiClient.post("/admin/skills/import-from-seed");
  return response.data;
}
