import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/stores/auth";

const pushMock = vi.fn();
const getMyDashboardMock = vi.fn();
const getMyCreditHistoryMock = vi.fn();
const redeemCreditCodeMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/components/layout/header", () => ({
  Header: () => <div data-testid="header" />,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getMyDashboard: (...args: unknown[]) => getMyDashboardMock(...args),
    getMyCreditHistory: (...args: unknown[]) => getMyCreditHistoryMock(...args),
    redeemCreditCode: (...args: unknown[]) => redeemCreditCodeMock(...args),
  };
});

import MyDashboardPage from "@/app/dashboard/me/page";

function dashboardPayload(balance: number) {
  return {
    profile: {
      id: "user-1",
      email: "ze@example.com",
      name: "Ze",
      role: "user",
      is_active: true,
      created_at: null,
      last_login: null,
    },
    credits: {
      balance,
      total_earned: balance,
      total_spent: 0,
      costs: {
        thread: { unit: "credits", pricing: "usage_based" },
      },
      thread: {
        enabled: true,
        can_start_thread: true,
        overdraft_credits: 0,
        billing_unit: "credits",
        pricing: "usage_based",
      },
    },
    workspaces: { total: 0, by_type: {}, created_last_7d: 0 },
    tasks: {
      total: 0,
      success: 0,
      running: 0,
      failed: 0,
      pending: 0,
      cancelled: 0,
      completion_rate: 0,
    },
    recent_tasks: [],
    updated_at: "2026-05-30T00:00:00Z",
  };
}

describe("MyDashboardPage credit redeem", () => {
  beforeEach(() => {
    pushMock.mockReset();
    getMyDashboardMock.mockReset();
    getMyCreditHistoryMock.mockReset();
    redeemCreditCodeMock.mockReset();
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "ze@example.com",
        name: "Ze",
        role: "user",
        credits: 0,
        total_credits_earned: 0,
        total_credits_spent: 0,
      },
      accessToken: "token",
      refreshToken: "refresh",
      isAuthenticated: true,
      isLoading: false,
      error: null,
    });
  });

  it("redeems a credit code from personal center and refreshes the credit dashboard", async () => {
    getMyDashboardMock
      .mockResolvedValueOnce(dashboardPayload(1000))
      .mockResolvedValueOnce(dashboardPayload(1200));
    getMyCreditHistoryMock
      .mockResolvedValueOnce({ transactions: [], total: 0, page: 1, page_size: 20, has_more: false })
      .mockResolvedValueOnce({
        transactions: [
          {
            id: "tx-1",
            type: "redeem_code",
            amount: 200,
            balance_after: 1200,
            description: "兑换码充值",
            metadata: {},
            created_at: "2026-05-30T00:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        has_more: false,
      });
    redeemCreditCodeMock.mockResolvedValueOnce({
      amount: 200,
      balance_after: 1200,
      transaction_id: "tx-1",
    });

    render(<MyDashboardPage />);

    expect(await screen.findByText("当前积分")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("兑换码"), {
      target: { value: " welcome200 " },
    });
    fireEvent.click(screen.getByRole("button", { name: "立即兑换" }));

    await waitFor(() => {
      expect(redeemCreditCodeMock).toHaveBeenCalledWith("welcome200");
    });
    expect(await screen.findByText("兑换成功，已到账 200 积分。")).toBeInTheDocument();
    expect(screen.getByText("1,200")).toBeInTheDocument();
    expect(useAuthStore.getState().user?.credits).toBe(1200);
    expect(getMyDashboardMock).toHaveBeenCalledTimes(2);
    expect(getMyCreditHistoryMock).toHaveBeenCalledTimes(2);
  });
});
