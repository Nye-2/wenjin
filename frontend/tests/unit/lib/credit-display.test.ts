import { describe, expect, it } from "vitest";

import {
  formatCreditCostLabel,
  getThreadCreditStatus,
  renderCostValue,
  summarizeCreditTransaction,
} from "@/lib/credit-display";

describe("credit-display", () => {
  it("renders public billing costs without token policy details", () => {
    expect(formatCreditCostLabel("thread")).toBe("主线对话");
    expect(formatCreditCostLabel("mission")).toBe("研究任务");
    expect(formatCreditCostLabel("sandbox_run_python")).toBe("实验环境 Python");
    expect(
      renderCostValue({
        enabled: true,
        unit: "credits",
        pricing: "usage_based",
      })
    ).toBe("按实际使用折算积分");
    expect(
      renderCostValue({
        enabled: true,
        unit: "credits",
        credits: 1,
      })
    ).toBe("1 积分/次");
  });

  it("parses thread credit status without token fields", () => {
    expect(
      getThreadCreditStatus({
        balance: 5,
        total_earned: 10,
        total_spent: 5,
        costs: {},
        thread: {
          enabled: true,
          can_start_thread: true,
          overdraft_credits: 0,
          billing_unit: "credits",
          pricing: "usage_based",
        },
      })
    ).toEqual({
      enabled: true,
      can_start_thread: true,
      overdraft_credits: 0,
      billing_unit: "credits",
      pricing: "usage_based",
    });
  });

  it("summarizes token-settled transactions as credit charges only", () => {
    const summary = summarizeCreditTransaction({
      id: "tx-1",
      type: "workflow_consume",
      amount: -2,
      balance_after: 8,
      description: "研究任务扣费 2 积分",
      mission_policy_id: "draft",
      metadata: {
        type: "mission_token_billing",
        token_usage: {
          total_tokens: 15000,
        },
        billable_tokens: 15000,
        credits_charged: 2,
      },
      created_at: "2026-05-30T00:00:00Z",
    });

    expect(summary).toContain("2 积分");
    expect(summary.toLowerCase()).not.toContain("token");
  });
});
