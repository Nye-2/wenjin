import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { WorkspaceChrome } from "@/app/(workbench)/workspaces/[id]/components/shell/WorkspaceChrome";
import { useAuthStore } from "@/stores/auth";

function clearAuthCookie() {
  document.cookie = "auth-storage=; Path=/; Max-Age=0; SameSite=Lax";
}

describe("WorkspaceChrome auth routing", () => {
  beforeEach(() => {
    localStorage.clear();
    clearAuthCookie();
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "user@example.com",
        name: "User",
        role: "user",
      },
      accessToken: "access-token",
      refreshToken: "refresh-token",
      isAuthenticated: true,
      isLoading: false,
      error: null,
    });
  });

  it("does not write route cookies when switching protected surfaces", () => {
    render(
      <WorkspaceChrome
        workspaceId="ws-1"
        workspaceName="Workspace"
        workspaceTypeLabel="SCI论文"
        activeSurface="workbench"
        pendingReviewCount={0}
        activeRunCount={0}
        onOpenHub={() => undefined}
      />,
    );

    expect(document.cookie).not.toContain("auth-storage=");

    const prismTab = screen.getByRole("tab", { name: "Prism" });
    prismTab.addEventListener("click", (event) => event.preventDefault());

    fireEvent.click(prismTab);

    expect(document.cookie).not.toContain("auth-storage=");
  });
});
