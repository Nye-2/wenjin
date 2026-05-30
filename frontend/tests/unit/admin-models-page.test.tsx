import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const listAdminModels = vi.fn();
const createAdminModel = vi.fn();
const updateAdminModel = vi.fn();
const disableAdminModel = vi.fn();
const setDefaultAdminModel = vi.fn();
const testAdminModel = vi.fn();

vi.mock("@/lib/api/admin-models", () => ({
  listAdminModels: (...args: unknown[]) => listAdminModels(...args),
  createAdminModel: (...args: unknown[]) => createAdminModel(...args),
  updateAdminModel: (...args: unknown[]) => updateAdminModel(...args),
  disableAdminModel: (...args: unknown[]) => disableAdminModel(...args),
  setDefaultAdminModel: (...args: unknown[]) => setDefaultAdminModel(...args),
  testAdminModel: (...args: unknown[]) => testAdminModel(...args),
}));

import AdminModelsPage from "@/app/dashboard/admin/models/page";

const MODEL = {
  id: "row-1",
  model_id: "deepseek-chat",
  display_name: "DeepSeek Chat",
  provider_protocol: "openai_compatible",
  provider_name: "DeepSeek",
  category: "llm",
  model_name: "deepseek-chat",
  base_url: "https://api.example.com/v1",
  api_key_redacted: "sk-****1234",
  enabled: true,
  is_default: true,
  supports_streaming: true,
  supports_tools: true,
  supports_json_mode: true,
  supports_json_schema: false,
  supports_vision: false,
  supports_reasoning_effort: false,
  max_tokens: 4096,
  temperature: 0.7,
  timeout_seconds: null,
  max_retries: null,
  trust_level: "custom",
  pricing_policy_id: "deepseek-policy",
  config_version: 1,
  health_status: "healthy",
  last_tested_at: null,
  last_test_error: null,
  default_headers: {},
  created_at: null,
  updated_at: null,
};

describe("AdminModelsPage", () => {
  beforeEach(() => {
    listAdminModels.mockReset().mockResolvedValue({ items: [MODEL], total: 1 });
    createAdminModel.mockReset().mockResolvedValue(MODEL);
    updateAdminModel.mockReset().mockResolvedValue(MODEL);
    disableAdminModel.mockReset().mockResolvedValue({ ...MODEL, enabled: false });
    setDefaultAdminModel.mockReset().mockResolvedValue(MODEL);
    testAdminModel.mockReset().mockResolvedValue(MODEL);
  });

  it("redacts API keys in the model table", async () => {
    render(<AdminModelsPage />);

    expect(await screen.findByText("sk-****1234")).toBeInTheDocument();
    expect(screen.queryByText("sk-test")).not.toBeInTheDocument();
  });

  it("does not send empty API key when saving an existing model", async () => {
    render(<AdminModelsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "编辑 deepseek-chat" }));
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(updateAdminModel).toHaveBeenCalled());
    expect(updateAdminModel).toHaveBeenCalledWith(
      "deepseek-chat",
      expect.not.objectContaining({
        api_key: expect.anything(),
        category: expect.anything(),
        enabled: expect.anything(),
      }),
    );
  });

  it("shows an error before disabling the default model", async () => {
    render(<AdminModelsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "禁用 deepseek-chat" }));

    expect(screen.getByText("默认模型不能直接禁用，请先设置新的默认模型。")).toBeInTheDocument();
    expect(disableAdminModel).not.toHaveBeenCalled();
  });
});
