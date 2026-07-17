import { apiClient } from "@/lib/api/client";
import type {
  AdminModelCatalogItem,
  ModelGenerationApi,
} from "@/lib/api/types";

export type AdminModelCreatePayload = {
  model_id: string;
  display_name: string;
  generation_api: ModelGenerationApi | null;
  provider_name?: string;
  category?: string;
  model_name: string;
  base_url: string;
  api_key: string;
  enabled?: boolean;
  is_default?: boolean;
  max_tokens?: number;
  temperature?: number;
  timeout_seconds?: number | null;
  max_retries?: number | null;
  trust_level?: string;
  pricing_policy_id?: string | null;
  default_headers?: Record<string, unknown>;
};

export type AdminModelUpdatePayload = Partial<Omit<AdminModelCreatePayload, "model_id">> & {
  model_id?: string;
};

export async function listAdminModels(params?: {
  category?: string;
  enabled_only?: boolean;
}): Promise<{ items: AdminModelCatalogItem[]; total: number }> {
  const response = await apiClient.get("/admin/models", { params });
  return response.data;
}

export async function createAdminModel(
  payload: AdminModelCreatePayload,
): Promise<AdminModelCatalogItem> {
  const response = await apiClient.post("/admin/models", payload);
  return response.data;
}

export async function updateAdminModel(
  modelId: string,
  payload: AdminModelUpdatePayload,
): Promise<AdminModelCatalogItem | null> {
  const cleaned = { ...payload };
  if (!String(cleaned.api_key ?? "").trim()) {
    delete cleaned.api_key;
  }
  const response = await apiClient.patch(`/admin/models/${encodeURIComponent(modelId)}`, cleaned);
  return response.data;
}

export async function disableAdminModel(modelId: string): Promise<AdminModelCatalogItem | null> {
  const response = await apiClient.post(`/admin/models/${encodeURIComponent(modelId)}/disable`);
  return response.data;
}

export async function setDefaultAdminModel(modelId: string): Promise<AdminModelCatalogItem | null> {
  const response = await apiClient.post(`/admin/models/${encodeURIComponent(modelId)}/set-default`);
  return response.data;
}

export async function testAdminModel(modelId: string): Promise<AdminModelCatalogItem | null> {
  const response = await apiClient.post(`/admin/models/${encodeURIComponent(modelId)}/test`);
  return response.data;
}
