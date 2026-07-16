import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { WorkspaceChrome } from "@/app/(workbench)/workspaces/[id]/components/shell/WorkspaceChrome";
import { WenjinThemeProvider } from "@/components/wenjin-theme-provider";
import { DEFAULT_WENJIN_THEME } from "@/lib/wenjin-theme";
import { useWenjinThemeStore } from "@/stores/wenjin-theme-store";

describe("WorkspaceChrome", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.setAttribute("data-wjn-theme", DEFAULT_WENJIN_THEME);
    useWenjinThemeStore.setState({ theme: DEFAULT_WENJIN_THEME });
  });

  it("renders one trusted chrome with surface switch and hub entry without exposing the raw workspace id", () => {
    render(
      <WorkspaceChrome
        workspaceId="787153c9-3e09-4a48-b683-e261bf8d18b3"
        workspaceName="Federated LLM Study"
        workspaceTypeLabel="SCI论文"
        activeSurface="workbench"
        pendingReviewCount={2}
        missionStatus="running"
        onOpenHub={() => undefined}
      />,
    );

    expect(screen.getByRole("link", { name: "Wenjin" })).toHaveAttribute(
      "href",
      "/workspaces",
    );
    expect(screen.getByRole("tab", { name: "工作台" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "写作台，2 项待确认" })).toHaveAttribute(
      "href",
      "/workspaces/787153c9-3e09-4a48-b683-e261bf8d18b3/prism",
    );
    expect(
      screen.getByRole("button", { name: "资料库，2 项待确认" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "启动任务、查找资料或召集团队" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Federated LLM Study")).toBeInTheDocument();
    expect(screen.getByText("运行中")).toBeInTheDocument();
    expect(screen.getByText("待确认")).toBeInTheDocument();
    expect(screen.queryByText("787153")).not.toBeInTheDocument();
  });

  it("switches between standard and eye comfort themes from the trusted chrome", async () => {
    render(
      <WenjinThemeProvider>
        <WorkspaceChrome
          workspaceId="ws-1"
          workspaceName="Federated LLM Study"
          workspaceTypeLabel="SCI论文"
          activeSurface="workbench"
          pendingReviewCount={0}
          missionStatus={null}
          onOpenHub={() => undefined}
        />
      </WenjinThemeProvider>,
    );

    expect(document.documentElement).toHaveAttribute("data-wjn-theme", "mineral");

    fireEvent.click(screen.getByRole("button", { name: "切换到护眼模式" }));

    await waitFor(() => {
      expect(document.documentElement).toHaveAttribute("data-wjn-theme", "graphite");
    });
    expect(screen.getByRole("button", { name: "切换到标准模式" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("distinguishes a mission waiting for the user from active research", () => {
    render(
      <WorkspaceChrome
        workspaceId="ws-waiting"
        workspaceName="Waiting Mission"
        workspaceTypeLabel="软著"
        activeSurface="workbench"
        pendingReviewCount={1}
        missionStatus="waiting"
        onOpenHub={() => undefined}
      />,
    );

    expect(screen.getByText("等待回应")).toBeInTheDocument();
    expect(screen.queryByText("运行中")).not.toBeInTheDocument();
  });
});
