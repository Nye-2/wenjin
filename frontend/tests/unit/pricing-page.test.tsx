import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import PricingPage from "@/app/pricing/page";

describe("PricingPage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("explains credit-based pricing without turning the home hero into a billing surface", () => {
    render(<PricingPage />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "清晰的 credits 定价，按科研任务实际使用结算。",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("当前阶段采用 credits 积分结算")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看积分后台" })).toHaveAttribute(
      "href",
      "/dashboard/me",
    );
    expect(screen.getAllByRole("link", { name: "进入工作台" })[0]).toHaveAttribute(
      "href",
      "/workspaces",
    );
  });
});
