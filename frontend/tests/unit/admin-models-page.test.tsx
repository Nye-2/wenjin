import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const listAdminModels = vi.fn();
const createAdminModel = vi.fn();
const updateAdminModel = vi.fn();
const disableAdminModel = vi.fn();
const setDefaultAdminModel = vi.fn();
const testAdminModel = vi.fn();
const listPricingPolicies = vi.fn();

vi.mock("@/lib/api/admin-models", () => ({
  listAdminModels: (...args: unknown[]) => listAdminModels(...args),
  createAdminModel: (...args: unknown[]) => createAdminModel(...args),
  updateAdminModel: (...args: unknown[]) => updateAdminModel(...args),
  disableAdminModel: (...args: unknown[]) => disableAdminModel(...args),
  setDefaultAdminModel: (...args: unknown[]) => setDefaultAdminModel(...args),
  testAdminModel: (...args: unknown[]) => testAdminModel(...args),
}));

vi.mock("@/lib/api/admin-pricing", () => ({
  listPricingPolicies: (...args: unknown[]) => listPricingPolicies(...args),
}));

import AdminModelsPage from "@/app/dashboard/admin/models/page";

const MODEL = {
  id: "row-1",
  model_id: "deepseek-chat",
  display_name: "DeepSeek Chat",
  generation_api: "chat_completions",
  provider_name: "DeepSeek",
  category: "llm",
  model_name: "deepseek-chat",
  base_url: "https://api.example.com/v1",
  api_key_redacted: "sk-****1234",
  enabled: true,
  is_default: true,
  capability_profile: {
    profile_version: "wenjin.model-capability-profile.v1",
    model_id: "deepseek-chat",
    generation_api: "chat_completions",
    structured_tool_calls: true,
    strict_tool_arguments: true,
    streaming: true,
    reasoning_efforts: ["low", "medium", "high", "xhigh"],
    native_web_search: true,
    web_search_api: "responses_web_search",
    search_receipts: ["web_search_call", "annotations_sources"],
    structured_outputs: true,
    vision: false,
    response_storage_disabled: true,
    protocol_conformance: true,
    transport_observations: [],
    observed_at: "2026-07-16T00:00:00Z",
    probe_hash: "a".repeat(64),
    endpoint_fingerprint: "b".repeat(64),
  },
  capability_probe: {
    probe_version: "wenjin.model-capability-probe.v1",
    model_id: "deepseek-chat",
    model_name: "deepseek-chat",
    generation_api: "chat_completions",
    endpoint_fingerprint: "b".repeat(64),
    observed_at: "2026-07-16T00:00:00Z",
    checks: [],
    web_search_api: "responses_web_search",
    search_receipts: ["web_search_call", "annotations_sources"],
    transport_observations: [],
  },
  capability_probe_hash: "a".repeat(64),
  capability_observed_at: "2026-07-16T00:00:00Z",
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

const MODEL_USAGE_POLICY = {
  id: "policy-row-1",
  policy_key: "deepseek-policy",
  policy_kind: "model_usage",
  name: "DeepSeek 计费策略",
  enabled: true,
  version: 1,
  config: { credits_per_1k_weighted_tokens: 6 },
  created_at: null,
  updated_at: null,
};

describe("AdminModelsPage", () => {
  beforeEach(() => {
    listAdminModels.mockReset().mockResolvedValue({ items: [MODEL], total: 1 });
    createAdminModel.mockReset().mockResolvedValue(MODEL);
    updateAdminModel.mockReset().mockResolvedValue(MODEL);
    disableAdminModel
      .mockReset()
      .mockResolvedValue({ ...MODEL, enabled: false });
    setDefaultAdminModel.mockReset().mockResolvedValue(MODEL);
    testAdminModel.mockReset().mockResolvedValue(MODEL);
    listPricingPolicies
      .mockReset()
      .mockResolvedValue({ items: [MODEL_USAGE_POLICY], total: 1 });
  });

  it("redacts API keys in the model table", async () => {
    render(<AdminModelsPage />);

    expect(await screen.findByText("sk-****1234")).toBeInTheDocument();
    expect(screen.queryByText("sk-test")).not.toBeInTheDocument();
  });

  it("does not send empty API key when saving an existing model", async () => {
    render(<AdminModelsPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: "编辑 deepseek-chat" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(updateAdminModel).toHaveBeenCalled());
    expect(updateAdminModel).toHaveBeenCalledWith(
      "deepseek-chat",
      expect.objectContaining({
        enabled: true,
      }),
    );
    expect(updateAdminModel).toHaveBeenCalledWith(
      "deepseek-chat",
      expect.not.objectContaining({
        api_key: expect.anything(),
        category: expect.anything(),
      }),
    );
  });

  it("shows an error before disabling the default model", async () => {
    render(<AdminModelsPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: "禁用 deepseek-chat" }),
    );

    expect(
      screen.getByText("默认模型不能直接禁用，请先设置新的默认模型。"),
    ).toBeInTheDocument();
    expect(disableAdminModel).not.toHaveBeenCalled();
  });

  it("can re-enable a disabled model from the table", async () => {
    listAdminModels.mockResolvedValue({
      items: [{ ...MODEL, enabled: false, is_default: false }],
      total: 1,
    });
    render(<AdminModelsPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: "启用 deepseek-chat" }),
    );

    await waitFor(() =>
      expect(updateAdminModel).toHaveBeenCalledWith("deepseek-chat", {
        enabled: true,
      }),
    );
  });

  it("loads model usage pricing policies when opening the model dialog", async () => {
    render(<AdminModelsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /新增模型/ }));

    await waitFor(() => {
      expect(listPricingPolicies).toHaveBeenCalledWith({
        policy_kind: "model_usage",
        enabled_only: true,
      });
    });
  });

  it("submits structured default headers when creating a model", async () => {
    render(<AdminModelsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /新增模型/ }));
    fireEvent.change(screen.getByLabelText("Model ID"), {
      target: { value: "kimi-code" },
    });
    fireEvent.change(screen.getByLabelText("显示名"), {
      target: { value: "Kimi Code" },
    });
    fireEvent.change(screen.getByLabelText("Model Name"), {
      target: { value: "kimi-for-coding" },
    });
    fireEvent.change(screen.getByLabelText("Base URL"), {
      target: { value: "https://api.kimi.com/coding/v1" },
    });
    fireEvent.change(screen.getByLabelText("API Key"), {
      target: { value: "sk-kimi-test" },
    });

    fireEvent.click(screen.getByRole("button", { name: "添加 Header" }));
    fireEvent.change(screen.getByLabelText("Header Key 1"), {
      target: { value: "api-key" },
    });
    fireEvent.change(screen.getByLabelText("Header Value 1"), {
      target: { value: "sk-kimi-test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(createAdminModel).toHaveBeenCalled());
    expect(createAdminModel).toHaveBeenCalledWith(
      expect.objectContaining({
        generation_api: "chat_completions",
        default_headers: { "api-key": "sk-kimi-test" },
      }),
    );
    expect(createAdminModel).toHaveBeenCalledWith(
      expect.not.objectContaining({
        provider_protocol: expect.anything(),
        supports_tools: expect.anything(),
      }),
    );
  });

  it("does not clear redacted default headers when editing headers", async () => {
    listAdminModels.mockResolvedValue({
      items: [
        {
          ...MODEL,
          default_headers: { "api-key": "[redacted]" },
        },
      ],
      total: 1,
    });
    render(<AdminModelsPage />);

    fireEvent.click(
      await screen.findByRole("button", { name: "编辑 deepseek-chat" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "添加 Header" }));
    fireEvent.change(screen.getByLabelText("Header Key 2"), {
      target: { value: "x-provider" },
    });
    fireEvent.change(screen.getByLabelText("Header Value 2"), {
      target: { value: "kimi" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    expect(
      await screen.findByText(
        "存在已脱敏 Header，修改 Headers 前请重新填写或删除该行。",
      ),
    ).toBeInTheDocument();
    expect(updateAdminModel).not.toHaveBeenCalled();
  });
});
