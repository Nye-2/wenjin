import { Suspense } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";

import PrismPage from "@/app/(workbench)/workspaces/[id]/prism/page";

const mockGetWorkspacePrismSurface = vi.hoisted(() => vi.fn());

vi.mock("@/components/latex/LatexEditorShell", () => ({
  LatexEditorShell: ({
    projectId,
    initialFileChanges = [],
  }: {
    projectId: string;
    initialFileChanges?: Array<unknown>;
  }) => (
    <div data-testid="latex-editor-shell">
      {projectId}:{initialFileChanges.length}
    </div>
  ),
}));

vi.mock("@/lib/api/workspace", () => ({
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
  review_items: [],
  source_links: [],
  protected_sections: [],
  decisions: [],
  memory_preferences: [],
  recent_activity: [],
  review_summary: {
    pending_count: 0,
    applied_count: 0,
    source_link_count: 0,
    protected_section_count: 0,
  },
  context_summary: {
    decision_count: 0,
    memory_preference_count: 0,
    recent_activity_count: 0,
  },
};

describe("workspace prism surface", () => {
  beforeEach(() => {
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
      "latex-1:0",
    );
  });

  it("does not create a workspace Prism binding from the surface route", async () => {
    const notFound = Object.assign(new Error("Workspace Prism surface not found"), {
      response: { status: 404 },
    });
    mockGetWorkspacePrismSurface.mockRejectedValue(notFound);

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <PrismPage params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>,
      );
    });

    expect(mockGetWorkspacePrismSurface).toHaveBeenCalledTimes(1);
    expect(
      await screen.findByText("Unable to open Prism manuscript surface"),
    ).toBeInTheDocument();
    expect(screen.getByText("Workspace Prism surface not found")).toBeInTheDocument();
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

  it("renders workspace manuscript context from the Prism surface projection", async () => {
    mockGetWorkspacePrismSurface.mockResolvedValue({
      ...prismSurface,
      has_pending_changes: true,
      file_changes: [
        {
          id: "review-1",
          logical_key: "section:introduction",
          path: "sections/introduction.tex",
          reason: "feature_proposal",
        },
      ],
      review_items: [
        {
          id: "review-1",
          kind: "prism_file_change",
          logical_key: "section:introduction",
          status: "pending",
          title: "Intro rewrite",
          summary: "feature_proposal",
          target: {
            kind: "prism_file_change",
            file_path: "sections/introduction.tex",
          },
        },
      ],
      source_links: [
        {
          id: "source-1",
          workspace_id: "ws-1",
          latex_project_id: "latex-1",
          review_item_id: "review-1",
          source_type: "library_item",
          source_id: "lib-1",
          file_path: "sections/introduction.tex",
          section_key: "section:introduction",
          quote: "important source excerpt",
          citation_key: "doe2026",
          usage: "citation",
        },
      ],
      protected_sections: [
        {
          id: "protected-1",
          workspace_id: "ws-1",
          latex_project_id: "latex-1",
          file_path: "sections/introduction.tex",
          section_key: "section:introduction",
          scope: "section",
          reason: "user_protected",
          source: "review_reject",
        },
      ],
      decisions: [
        {
          id: "decision-1",
          workspace_id: "ws-1",
          key: "citation_style",
          value: "APA 7",
          confidence: 1,
          extracted_by: "user",
        },
      ],
      memory_preferences: [
        {
          id: "memory-1",
          workspace_id: "ws-1",
          category: "writing_style",
          content: "Prefer concise topic sentences",
          confidence: 0.9,
          reference_count: 3,
        },
      ],
      recent_activity: [
        {
          id: "run-1",
          workspace_id: "ws-1",
          execution_id: "exec-1",
          capability_id: "writing",
          title: "Intro drafting",
          summary: "Generated manuscript update",
          status: "completed",
          artifact_count: 1,
          duration_seconds: 12,
        },
      ],
      review_summary: {
        pending_count: 1,
        applied_count: 0,
        source_link_count: 1,
        protected_section_count: 1,
      },
      context_summary: {
        decision_count: 1,
        memory_preference_count: 1,
        recent_activity_count: 1,
      },
    });

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <PrismPage params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>,
      );
    });

    expect(await screen.findByText("doe2026")).toBeInTheDocument();
    const sourceLink = screen.getByRole("link", { name: /doe2026/ });
    expect(sourceLink).toHaveAttribute(
      "href",
      "/workspaces/ws-1?room=library&item_id=lib-1",
    );
    expect(screen.getByTestId("latex-editor-shell")).toHaveTextContent("latex-1:1");
    expect(screen.getByText("important source excerpt")).toBeInTheDocument();
    expect(screen.getByText("user_protected")).toBeInTheDocument();
    expect(screen.getByText("citation_style")).toBeInTheDocument();
    expect(screen.getByText("APA 7")).toBeInTheDocument();
    expect(screen.getByText("Prefer concise topic sentences")).toBeInTheDocument();
    expect(screen.getByText("Intro drafting")).toBeInTheDocument();
  });
});
