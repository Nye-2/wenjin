import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkspaceActionLink } from "@/app/(workbench)/workspaces/[id]/components/WorkspaceActionLink";

describe("WorkspaceActionLink", () => {
  it("keeps workspace-internal hrefs as in-app navigation links", () => {
    render(
      <WorkspaceActionLink href="/workspaces/ws-1?room=documents">
        打开文档
      </WorkspaceActionLink>,
    );

    const link = screen.getByRole("link", { name: "打开文档" });
    expect(link).toHaveAttribute("href", "/workspaces/ws-1?room=documents");
    expect(link).not.toHaveAttribute("target");
  });

  it("preserves new-tab behavior for external links", () => {
    render(
      <WorkspaceActionLink href="https://example.com/paper">
        外部论文
      </WorkspaceActionLink>,
    );

    const link = screen.getByRole("link", { name: "外部论文" });
    expect(link).toHaveAttribute("href", "https://example.com/paper");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });
});
