import { Suspense } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import PrismPage from "@/app/(workbench)/workspaces/[id]/prism/page";

const mockGetWorkspacePrismSurface = vi.hoisted(() => vi.fn());
const mockEnsureWorkspacePrismProject = vi.hoisted(() => vi.fn());
const mockGetWorkspacePrismFile = vi.hoisted(() => vi.fn());
const mockSaveWorkspacePrismFile = vi.hoisted(() => vi.fn());
const mockCreateWorkspacePrismFile = vi.hoisted(() => vi.fn());
const mockGetWorkspace = vi.hoisted(() => vi.fn());
const mockRouterPush = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush }),
  useSearchParams: () => new URLSearchParams(),
}));

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
  ensureWorkspacePrismProject: (...args: unknown[]) =>
    mockEnsureWorkspacePrismProject(...args),
  createWorkspacePrismFile: (...args: unknown[]) =>
    mockCreateWorkspacePrismFile(...args),
  getWorkspacePrismFile: (...args: unknown[]) =>
    mockGetWorkspacePrismFile(...args),
  getWorkspace: (...args: unknown[]) => mockGetWorkspace(...args),
  getWorkspacePrismSurface: (...args: unknown[]) =>
    mockGetWorkspacePrismSurface(...args),
  saveWorkspacePrismFile: (...args: unknown[]) =>
    mockSaveWorkspacePrismFile(...args),
}));

const prismSurface = {
  workspace_id: "ws-1",
  latex_project_id: "latex-1",
  surface_role: "primary_manuscript",
  url: "/workspaces/ws-1/prism",
  main_file: "main.tex",
  prism_project_id: "prism-1",
  prism_document_id: "document-1",
  prism_files: [
    {
      id: "file-main",
      workspace_id: "ws-1",
      document_id: "document-1",
      path: "main.tex",
      file_role: "main",
      mime_type: "text/x-tex",
      current_version_id: "version-main",
      content_hash: "sha256:main",
      sort_order: 0,
      metadata_json: {},
      deleted_at: null,
      created_at: null,
      updated_at: null,
    },
    {
      id: "file-readme",
      workspace_id: "ws-1",
      document_id: "document-1",
      path: "docs/readme.md",
      file_role: "manual",
      mime_type: "text/markdown",
      current_version_id: "version-readme",
      content_hash: "sha256:readme",
      sort_order: 1,
      metadata_json: {},
      deleted_at: null,
      created_at: null,
      updated_at: null,
    },
  ],
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
  afterEach(() => {
    vi.useRealTimers();
  });

  beforeEach(() => {
    mockEnsureWorkspacePrismProject.mockReset();
    mockEnsureWorkspacePrismProject.mockResolvedValue({
      latex_project_id: "latex-1",
      prism_project_id: "prism-1",
      url: "/workspaces/ws-1/prism",
      sync_status: "ready",
    });
    mockGetWorkspacePrismFile.mockReset();
    mockGetWorkspacePrismFile.mockResolvedValue({
      file: prismSurface.prism_files[0],
      current_version: {
        id: "version-main",
        workspace_id: "ws-1",
        file_id: "file-main",
        version_no: 1,
        review_item_id: null,
        content_inline: "\\section{Intro}",
        content_asset_id: null,
        content_hash: "sha256:main",
        created_by: "system",
        created_at: null,
        updated_at: null,
      },
    });
    mockSaveWorkspacePrismFile.mockReset();
    mockSaveWorkspacePrismFile.mockResolvedValue({
      file: { ...prismSurface.prism_files[0], content_hash: "sha256:saved" },
      version: {
        id: "version-saved",
        workspace_id: "ws-1",
        file_id: "file-main",
        version_no: 2,
        review_item_id: null,
        content_inline: "\\section{Updated}",
        content_asset_id: null,
        content_hash: "sha256:saved",
        created_by: "user-1",
        created_at: null,
        updated_at: null,
      },
      changed: true,
      skipped_reason: null,
    });
    mockCreateWorkspacePrismFile.mockReset();
    mockGetWorkspace.mockReset();
    mockGetWorkspace.mockResolvedValue({
      id: "ws-1",
      name: "Federated LLM Study",
      type: "sci",
    });
    mockRouterPush.mockReset();
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

    expect(screen.getByRole("tab", { name: "写作台" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "工作台" })).toHaveAttribute(
      "href",
      "/workspaces/ws-1",
    );
    expect(await screen.findByTestId("prism-studio-shell")).toBeInTheDocument();
    expect(await screen.findByTestId("prism-workspace-shell")).toBeInTheDocument();
    expect(await screen.findByTestId("prism-file-editor")).toHaveValue("\\section{Intro}");
  });

  it("routes workspace hub entries back to the workbench rooms", async () => {
    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <PrismPage params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>,
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "资料库" }));
    fireEvent.click(screen.getByRole("button", { name: "文献资料" }));

    expect(mockRouterPush).toHaveBeenCalledWith("/workspaces/ws-1?room=library");
  });

  it("ensures a workspace Prism binding before loading the surface", async () => {
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

    expect(mockEnsureWorkspacePrismProject).toHaveBeenCalledWith("ws-1");
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
      "正在打开论文写作台",
    );
    expect(screen.getByTestId("workspace-surface-state")).toHaveTextContent(
      "正在加载工作区主稿和待复核修改。",
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

  it("renders the file workspace when no manuscript project is bound", async () => {
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

    expect(await screen.findByTestId("prism-workspace-shell")).toBeInTheDocument();
    expect(await screen.findByTestId("prism-file-editor")).toHaveValue("\\section{Intro}");
  });

  it("renders markdown preview for markdown files", async () => {
    mockGetWorkspacePrismFile.mockImplementation(async (_workspaceId: string, fileId: string) => {
      if (fileId === "file-readme") {
        return {
          file: prismSurface.prism_files[1],
          current_version: {
            id: "version-readme",
            workspace_id: "ws-1",
            file_id: "file-readme",
            version_no: 1,
            review_item_id: null,
            content_inline: "# 申报材料\n\n- 用户端截图",
            content_asset_id: null,
            content_hash: "sha256:readme",
            created_by: "system",
            created_at: null,
            updated_at: null,
          },
        };
      }
      return {
        file: prismSurface.prism_files[0],
        current_version: {
          id: "version-main",
          workspace_id: "ws-1",
          file_id: "file-main",
          version_no: 1,
          review_item_id: null,
          content_inline: "\\section{Intro}",
          content_asset_id: null,
          content_hash: "sha256:main",
          created_by: "system",
          created_at: null,
          updated_at: null,
        },
      };
    });

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <PrismPage params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>,
      );
    });

    fireEvent.click(await screen.findByTestId("prism-file-file-readme"));

    expect(await screen.findByRole("heading", { name: "申报材料" })).toBeInTheDocument();
    expect(screen.getByText("用户端截图")).toBeInTheDocument();
  });

  it("autosaves text edits without a save button", async () => {
    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <PrismPage params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>,
      );
    });

    const editor = await screen.findByTestId("prism-file-editor");
    vi.useFakeTimers();
    fireEvent.change(editor, { target: { value: "\\section{Updated}" } });
    expect(screen.getByTestId("prism-save-state")).toHaveTextContent("未保存");

    await act(async () => {
      vi.advanceTimersByTime(1600);
    });
    vi.useRealTimers();

    await waitFor(() => expect(mockSaveWorkspacePrismFile).toHaveBeenCalledTimes(1));
    expect(mockSaveWorkspacePrismFile.mock.calls[0][2]).toMatchObject({
      content_inline: "\\section{Updated}",
      expected_current_hash: "sha256:main",
    });
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
      memory_preferences: [],
      recent_activity: [
        {
          id: "run-1",
          workspace_id: "ws-1",
          mission_id: "mission-1",
          mission_policy_id: "thesis",
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
        memory_preference_count: 0,
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
    expect(screen.getByTestId("prism-workspace-shell")).toBeInTheDocument();
    expect(screen.getAllByText("待复核").length).toBeGreaterThan(0);
    expect(screen.getByText("来源")).toBeInTheDocument();
    expect(screen.getByText("活动")).toBeInTheDocument();
    expect(screen.getByText("保护段落")).toBeInTheDocument();
  });
});
