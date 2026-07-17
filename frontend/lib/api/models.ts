import { apiClient } from "@/lib/api/client";
import type {
  Model,
  ModelGenerationApi,
  ModelPurpose,
} from "@/lib/api/types";

interface ModelWireItem {
  name: string;
  display_name: string;
  category?: string;
  provider: string;
  max_tokens: number;
  generation_api: ModelGenerationApi | null;
  capability_profile_version: string;
  strict_tool_calls: boolean;
  streaming: boolean;
  reasoning_efforts: Model["capability_profile"]["reasoning_efforts"];
  vision: boolean;
  native_web_search: boolean;
  is_default?: boolean;
}

export async function listModels(
  purpose: ModelPurpose = "chat"
): Promise<{ models: Model[] }> {
  const response = await apiClient.get("/models", {
    params: { purpose },
  });
  const data = response.data as
    | ModelWireItem[]
    | { models?: ModelWireItem[]; items?: ModelWireItem[] };
  const items = Array.isArray(data)
    ? data
    : Array.isArray(data.models)
      ? data.models
      : Array.isArray(data.items)
        ? data.items
        : [];
  return {
    models: items.map((item) => ({
      name: item.name,
      display_name: item.display_name,
      category: item.category,
      provider: item.provider,
      max_tokens: item.max_tokens,
      generation_api: item.generation_api,
      capability_profile_version: item.capability_profile_version,
      capability_profile: {
        strict_tool_calls: item.strict_tool_calls,
        streaming: item.streaming,
        reasoning_efforts: item.reasoning_efforts,
        vision: item.vision,
        native_web_search: item.native_web_search,
      },
      is_default: item.is_default,
    })),
  };
}
