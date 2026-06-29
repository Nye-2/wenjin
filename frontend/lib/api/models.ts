import { apiClient } from "@/lib/api/client";
import type { Model, ModelPurpose } from "@/lib/api/types";

export async function listModels(
  purpose: ModelPurpose = "chat"
): Promise<{ models: Model[] }> {
  const response = await apiClient.get("/models", {
    params: { purpose },
  });
  const data = response.data;
  if (Array.isArray(data)) {
    return { models: data };
  }
  if (Array.isArray(data?.models)) {
    return { models: data.models };
  }
  if (Array.isArray(data?.items)) {
    return { models: data.items };
  }
  return { models: [] };
}
