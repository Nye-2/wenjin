import { Suspense } from "react";
import { describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";

import PrismPage from "@/app/(workbench)/workspaces/[id]/prism/page";

vi.mock("@/components/latex/LatexEditorShell", () => ({
  LatexEditorShell: ({ projectId }: { projectId: string }) => (
    <div data-testid="latex-editor-shell">{projectId}</div>
  ),
}));

vi.mock("@/lib/api/workspace", () => ({
  getWorkspacePrismSurface: vi.fn(async (workspaceId: string) => ({
    workspace_id: workspaceId,
    latex_project_id: "latex-1",
    surface_role: "primary_manuscript",
    url: `/workspaces/${workspaceId}/prism`,
    main_file: "main.tex",
    compile_status: null,
    has_pending_changes: false,
    file_changes: [],
    applied_file_changes: [],
  })),
}));

describe("workspace prism surface", () => {
  it("renders the manuscript surface switch as active", async () => {
    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <PrismPage params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>,
      );
    });

    expect(screen.getByRole("tab", { name: "Prism" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "Workbench" })).toHaveAttribute(
      "href",
      "/workspaces/ws-1",
    );
    expect(await screen.findByTestId("latex-editor-shell")).toHaveTextContent(
      "latex-1",
    );
  });
});
