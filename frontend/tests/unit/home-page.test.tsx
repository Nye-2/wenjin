import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/stores/auth";
import { useLocaleStore } from "@/stores/locale";

const pushMock = vi.fn();
let HomePage: typeof import("@/app/page").default;

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/components/i18n-provider", () => ({
  useI18n: () => ({
    locale: "cn",
    t: (key: string) =>
      ({
        "nav.creditBalance": "当前积分",
        "nav.creditDashboard": "查看积分后台",
        "nav.userDashboard": "账户概览",
        "nav.workspaces": "工作空间",
        "nav.settings": "设置",
        "nav.logout": "退出登录",
      })[key] ?? key,
  }),
}));

describe("HomePage", () => {
  beforeAll(async () => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    class MockIntersectionObserver {
      observe = vi.fn();
      unobserve = vi.fn();
      disconnect = vi.fn();
      takeRecords = vi.fn(() => []);
    }
    Object.defineProperty(window, "IntersectionObserver", {
      writable: true,
      value: MockIntersectionObserver,
    });
    Object.defineProperty(globalThis, "IntersectionObserver", {
      writable: true,
      value: MockIntersectionObserver,
    });

    HomePage = (await import("@/app/page")).default;
  });

  beforeEach(() => {
    pushMock.mockReset();
    localStorage.clear();
    useLocaleStore.setState({ locale: "cn" });
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    });
  });

  it("renders the brand-first hero with a real product visual and product sections", () => {
    render(<HomePage />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "问津 Wenjin",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "从一个研究想法开始，Agent 组织文献、证据、实验与稿件；你在 Prism 里确认引用、修改和最终成稿。",
      ),
    ).toBeInTheDocument();
    const heroVisualSrc = screen.getByTestId("landing-hero-visual").getAttribute("src") ?? "";
    expect(decodeURIComponent(heroVisualSrc)).toContain("/hero-prism-workbench.jpg");
    expect(screen.queryByText("点击播放产品演示")).not.toBeInTheDocument();
    expect(screen.getByText("不是聊天框，也不是模板库。它是研究任务的执行环境。")).toBeInTheDocument();
    expect(screen.getByText("用户掌方向，Agent 跑链路。")).toBeInTheDocument();
  });

  it("moves credits into the signed-in avatar menu and keeps pricing in the nav", () => {
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "ze@example.com",
        name: "Ze",
        role: "user",
        credits: 1280,
        total_credits_earned: 2000,
        total_credits_spent: 720,
      },
      accessToken: "token",
      refreshToken: "refresh",
      isAuthenticated: true,
      isLoading: false,
      error: null,
    });

    render(<HomePage />);

    expect(screen.getByRole("link", { name: "定价" })).toHaveAttribute(
      "href",
      "/pricing",
    );
    expect(screen.queryByRole("link", { name: /1280 credits/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Ze/ }));

    expect(screen.getByText("当前积分")).toBeInTheDocument();
    expect(screen.getByText("1,280")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看积分后台" }));
    expect(pushMock).toHaveBeenCalledWith("/dashboard/me");
    expect(screen.queryByRole("button", { name: "登录" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "注册" })).not.toBeInTheDocument();
  });

  it("shows login and register actions for signed-out users", () => {
    render(<HomePage />);

    expect(screen.getByRole("button", { name: "登录" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "注册" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "定价" })).toHaveAttribute(
      "href",
      "/pricing",
    );
    expect(screen.queryByRole("link", { name: /credits/ })).not.toBeInTheDocument();
  });

  it("opens quick start choices with the five workspace types", () => {
    render(<HomePage />);

    fireEvent.click(screen.getByRole("button", { name: "快速开始" }));

    expect(screen.getByRole("link", { name: "SCI" })).toHaveAttribute(
      "href",
      "/workspaces?create=sci",
    );
    expect(screen.getByRole("link", { name: "学位论文" })).toHaveAttribute(
      "href",
      "/workspaces?create=thesis",
    );
    expect(screen.getByRole("link", { name: "项目书" })).toHaveAttribute(
      "href",
      "/workspaces?create=proposal",
    );
    expect(screen.getByRole("link", { name: "专利" })).toHaveAttribute(
      "href",
      "/workspaces?create=patent",
    );
    expect(screen.getByRole("link", { name: "软著" })).toHaveAttribute(
      "href",
      "/workspaces?create=software_copyright",
    );
  });

  it("switches the landing copy when language changes to English", () => {
    useLocaleStore.setState({ locale: "en" });

    render(<HomePage />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: "Wenjin",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "From a research idea, agents organize literature, evidence, experiments, and drafts while you confirm citations, edits, and final manuscript state in Prism.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Product")).toBeInTheDocument();
    expect(screen.getByText("Pricing")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Quick Start" })).toBeInTheDocument();
  });
});
