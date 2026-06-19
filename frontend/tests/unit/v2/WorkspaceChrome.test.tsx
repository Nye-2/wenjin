import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkspaceChrome } from "@/app/(workbench)/workspaces/[id]/components/shell/WorkspaceChrome";

describe("WorkspaceChrome", () => {
  it("renders one trusted chrome with surface switch and hub entry without exposing the raw workspace id", () => {
    render(
      <WorkspaceChrome
        workspaceId="787153c9-3e09-4a48-b683-e261bf8d18b3"
        workspaceName="Federated LLM Study"
        workspaceTypeLabel="SCI论文"
        activeSurface="workbench"
        pendingReviewCount={2}
        activeRunCount={1}
        onOpenHub={() => undefined}
      />,
    );

    expect(screen.getByRole("link", { name: "Wenjin" })).toHaveAttribute(
      "href",
      "/workspaces",
    );
    expect(screen.getByRole("tab", { name: "Workbench" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "Prism，2 项待确认" })).toHaveAttribute(
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
});
