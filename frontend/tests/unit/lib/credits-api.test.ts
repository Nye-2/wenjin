import { beforeEach, describe, expect, it, vi } from "vitest";

const mockPost = vi.fn();

vi.mock("@/lib/api/client", () => ({
  apiClient: {
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

import { redeemCreditCode } from "@/lib/api/credits";

describe("credits api wrappers", () => {
  beforeEach(() => {
    mockPost.mockReset();
  });

  it("redeems user credit codes through the user-facing credits endpoint", async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        amount: 100,
        balance_after: 1200,
        transaction_id: "tx-1",
      },
    });

    const result = await redeemCreditCode(" abc-123 ");

    expect(mockPost).toHaveBeenCalledWith("/credits/redeem", {
      code: "ABC-123",
    });
    expect(result.balance_after).toBe(1200);
  });
});
