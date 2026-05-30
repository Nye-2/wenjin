import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
  },
}));

import {
  createPricingPolicy,
  listPricingPolicies,
  simulatePricing,
  updatePricingPolicy,
} from "@/lib/api/admin-pricing";

describe("admin pricing api wrappers", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockPatch.mockReset();
  });

  it("uses admin pricing endpoints", async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [], total: 0 } });
    mockPost
      .mockResolvedValueOnce({ data: { policy_key: "model-default" } })
      .mockResolvedValueOnce({ data: { charge_credits: 12 } });
    mockPatch.mockResolvedValueOnce({ data: { policy_key: "model-default" } });

    await listPricingPolicies({ policy_kind: "model_usage", enabled_only: true });
    await createPricingPolicy({
      policy_key: "model-default",
      policy_kind: "model_usage",
      name: "Model default",
      config: { credits_per_1k_weighted_tokens: 6 },
    });
    await updatePricingPolicy("model-default", { enabled: false });
    await simulatePricing({
      policy_kind: "model_usage",
      surface: "chat",
      prompt_tokens: 1000,
      completion_tokens: 500,
      global_policy: { credits_per_cny: 10 },
      model_usage_policy: { credits_per_1k_weighted_tokens: 6 },
    });

    expect(mockGet).toHaveBeenCalledWith("/admin/pricing-policies", {
      params: { policy_kind: "model_usage", enabled_only: true },
    });
    expect(mockPost).toHaveBeenNthCalledWith(1, "/admin/pricing-policies", {
      policy_key: "model-default",
      policy_kind: "model_usage",
      name: "Model default",
      config: { credits_per_1k_weighted_tokens: 6 },
    });
    expect(mockPatch).toHaveBeenCalledWith("/admin/pricing-policies/model-default", {
      enabled: false,
    });
    expect(mockPost).toHaveBeenNthCalledWith(2, "/admin/pricing/simulate", {
      policy_kind: "model_usage",
      surface: "chat",
      prompt_tokens: 1000,
      completion_tokens: 500,
      global_policy: { credits_per_cny: 10 },
      model_usage_policy: { credits_per_1k_weighted_tokens: 6 },
    });
  });
});
