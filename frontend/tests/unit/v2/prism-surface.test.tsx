import { Suspense } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";

import PrismPage from "@/app/(workbench)/workspaces/[id]/prism/page";

const mockEnsureWorkspacePrismProject = vi.hoisted(() => vi.fn());
const mockGetWorkspacePrismSurface = vi.hoisted(() => vi.fn());

vi.mock("@/components/latex/LatexEditorShell", () => ({
  LatexEditorShell: ({ projectId }: { projectId: string }) => (
    <div data-testid="latex-editor-shell">{projectId}</div>
  ),
}));

vi.mock("@/lib/api/workspace", () => ({
  ensureWorkspacePrismProject: (...args: unknown[]) =>
    mockEnsureWorkspacePrismProject(...args),
  getWorkspacePrismSurface: (...args: unknown[]) =>
    mockGetWorkspacePrismSurface(...args),
}));

const prismSurface = {
  workspace_id: "ws-1",
  latex_project_id: "latex-1",
  surface_role: "primary_manuscript",
  url: "/workspaces/ws-1/prism",
  main_file: "main.tex",
  compile_status: null,
  has_pending_changes: false,
  target_files: ["main.tex"],
  file_changes: [],
  applied_file_changes: [],
};

describe("workspace prism surface", () => {
  beforeEach(() => {
    mockEnsureWorkspacePrismProject.mockReset();
    mockEnsureWorkspacePrismProject.mockResolvedValue({
      latex_project_id: "latex-1",
      url: "/workspaces/ws-1/prism",
      sync_status: "ready",
    });
    mockGetWorkspacePrismSurface.mockReset();
    mockGetWorkspacePrismSurface.mockResolvedValue(prismSurface);
  });

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

  it("repairs a missing workspace Prism binding before opening the editor", async () => {
    const notFound = Object.assign(new Error("Workspace Prism surface not found"), {
      response: { status: 404 },
    });
    mockGetWorkspacePrismSurface
      .mockRejectedValueOnce(notFound)
      .mockResolvedValueOnce(prismSurface);

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <PrismPage params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>,
      );
    });

    expect(mockEnsureWorkspacePrismProject).toHaveBeenCalledWith("ws-1");
    expect(mockGetWorkspacePrismSurface).toHaveBeenCalledTimes(2);
    expect(await screen.findByTestId("latex-editor-shell")).toHaveTextContent(
      "latex-1",
    );
  });

  it("uses the shared surface state while loading", async () => {
    mockGetWorkspacePrismSurface.mockReturnValue(new Promise(() => {}));

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <PrismPage params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>,
      );
    });

    expect(screen.getByTestId("workspace-surface-state")).toHaveTextContent(
      "Opening Prism manuscript surface",
    );
  });

  it("uses the shared surface state for Prism load errors", async () => {
    mockGetWorkspacePrismSurface.mockRejectedValue(new Error("Prism unavailable"));

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <PrismPage params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>,
      );
    });

    expect(
      await screen.findByText("Unable to open Prism manuscript surface"),
    ).toBeInTheDocument();
    expect(screen.getByText("Prism unavailable")).toBeInTheDocument();
  });

  it("uses the shared surface state when no manuscript project is bound", async () => {
    mockGetWorkspacePrismSurface.mockResolvedValue({
      ...prismSurface,
      latex_project_id: null,
    });

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <PrismPage params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>,
      );
    });

    expect(
      await screen.findByText("No Prism manuscript is bound yet"),
    ).toBeInTheDocument();
  });
});
