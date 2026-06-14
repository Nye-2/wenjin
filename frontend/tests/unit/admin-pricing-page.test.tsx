import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const listPricingPolicies = vi.fn();
const createPricingPolicy = vi.fn();
const updatePricingPolicy = vi.fn();
const disablePricingPolicy = vi.fn();
const simulatePricing = vi.fn();

vi.mock("@/lib/api/admin-pricing", () => ({
  listPricingPolicies: (...args: unknown[]) => listPricingPolicies(...args),
  createPricingPolicy: (...args: unknown[]) => createPricingPolicy(...args),
  updatePricingPolicy: (...args: unknown[]) => updatePricingPolicy(...args),
  disablePricingPolicy: (...args: unknown[]) => disablePricingPolicy(...args),
  simulatePricing: (...args: unknown[]) => simulatePricing(...args),
}));

import AdminPricingPage from "@/app/dashboard/admin/credits/pricing/page";

const POLICY = {
  id: "policy-1",
  policy_key: "deepseek-policy",
  policy_kind: "model_usage",
  name: "DeepSeek 计费策略",
  enabled: true,
  version: 1,
  config: { credits_per_1k_weighted_tokens: 6 },
  created_at: null,
  updated_at: null,
};

describe("AdminPricingPage", () => {
  beforeEach(() => {
    listPricingPolicies
      .mockReset()
      .mockResolvedValue({ items: [POLICY], total: 1 });
    createPricingPolicy.mockReset().mockResolvedValue(POLICY);
    updatePricingPolicy.mockReset().mockResolvedValue(POLICY);
    disablePricingPolicy
      .mockReset()
      .mockResolvedValue({ ...POLICY, enabled: false });
    simulatePricing.mockReset().mockResolvedValue({
      charge_credits: 12,
      raw_cost_cny: 0.2,
      margin_cny: 1,
      breakdown: { weighted_tokens: 1800 },
    });
  });

  it("renders pricing policies", async () => {
    render(<AdminPricingPage />);

    expect(await screen.findByText("DeepSeek 计费策略")).toBeInTheDocument();
    expect(screen.getByText("model_usage")).toBeInTheDocument();
  });

  it("renders simulator credit estimate and margin", async () => {
    render(<AdminPricingPage />);

    const simulateButton = await screen.findByRole("button", {
      name: "估算积分",
    });
    await waitFor(() => expect(simulateButton).not.toBeDisabled());
    fireEvent.click(simulateButton);

    await waitFor(() => expect(simulatePricing).toHaveBeenCalled());
    expect(simulatePricing).toHaveBeenCalledWith(
      expect.objectContaining({
        model_usage_policy: POLICY.config,
      }),
    );
    expect(await screen.findByText("12 credits")).toBeInTheDocument();
    expect(screen.getByText("毛利 1 CNY")).toBeInTheDocument();
  });

  it("uses complete model-usage defaults in the create dialog", async () => {
    render(<AdminPricingPage />);

    fireEvent.click(await screen.findByRole("button", { name: /新增策略/ }));

    const config = screen.getByLabelText("Config JSON") as HTMLTextAreaElement;
    expect(config.value).toContain("cached_input_weight");
    expect(config.value).toContain("reasoning_weight");
    expect(config.value).toContain("raw_cost");
  });

  it("simulates with complete model-usage defaults when no active policy exists", async () => {
    listPricingPolicies.mockResolvedValue({ items: [], total: 0 });
    render(<AdminPricingPage />);

    const simulateButton = await screen.findByRole("button", {
      name: "估算积分",
    });
    await waitFor(() => expect(simulateButton).not.toBeDisabled());
    fireEvent.click(simulateButton);

    await waitFor(() => expect(simulatePricing).toHaveBeenCalled());
    expect(simulatePricing).toHaveBeenCalledWith(
      expect.objectContaining({
        model_usage_policy: expect.objectContaining({
          cached_input_weight: 0.05,
          reasoning_weight: 1,
          raw_cost: expect.objectContaining({
            input_usd_per_1m: 0,
            output_usd_per_1m: 0,
          }),
        }),
      }),
    );
  });
});
