import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ResultCard } from "@/app/(workbench)/workspaces/[id]/components/ResultCard";
import { useWorkbenchLayoutStore } from "@/stores/workbench-layout-store";

const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockResolvedValue({
    ok: true,
    json: () =>
      Promise.resolve({
        committed: {},
        room_targets: {
          documents: [{ output_id: "o3", item_id: "doc-77" }],
          library: [{ output_id: "o1", item_id: "lib-88" }],
          memory: [{ output_id: "o4", item_id: "mem-99" }],
        },
      }),
  });
  localStorage.clear();
  useWorkbenchLayoutStore.getState().reset();
});

const SAMPLE_DATA = {
  execution_id: "exec-1",
  capability_name: "文献检索",
  status: "completed" as const,
  duration_seconds: 23,
  narrative: "找到 15 篇相关文献",
  outputs: [
    {
      id: "o1",
      kind: "library_item" as const,
      preview: "Smith et al. 2024",
      default_checked: true,
      data: {
        title: "Deep Learning",
        authors: ["Smith"],
        year: 2024,
        abstract: "A compact survey of deep learning systems.",
      },
    },
    {
      id: "o2",
      kind: "library_item" as const,
      preview: "Wang et al. 2023",
      default_checked: true,
      data: {
        title: "Transformers",
        authors: ["Wang"],
        year: 2023,
      },
    },
    {
      id: "o3",
      kind: "document" as const,
      preview: "综述初稿",
      default_checked: false,
      data: {
        name: "综述初稿.md",
        mime_type: "text/markdown",
        doc_kind: "draft" as const,
        content: "# 综述\n- 研究背景",
      },
    },
    {
      id: "o4",
      kind: "memory_fact" as const,
      preview: "研究主题：联邦学习大模型",
      default_checked: true,
      data: {
        category: "context",
        content: "研究主题：联邦学习大模型",
        confidence: 0.9,
      },
    },
  ],
};

describe("ResultCard", () => {
  it("renders a compact result package instead of a long in-chat list", () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    expect(screen.getByText(/找到 15 篇相关文献/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看详情" })).toBeInTheDocument();
    expect(screen.getByText("文献资料")).toBeInTheDocument();
    expect(screen.getByText("文档产物")).toBeInTheDocument();
    expect(screen.getByText("记忆片段")).toBeInTheDocument();
    expect(screen.getByText("Deep Learning")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText("保存到工作区")).toBeInTheDocument();
  });

  it("opens the workbench review surface for detailed result review", () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    fireEvent.click(screen.getByRole("button", { name: "查看详情" }));

    expect(useWorkbenchLayoutStore.getState().selectedRunId).toBe("exec-1");
    expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("review");
    expect(useWorkbenchLayoutStore.getState().isWorkbenchFullscreen).toBe(true);
  });

  it("calls commit with accept_all on '保存到工作区'", async () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    fireEvent.click(screen.getByText("保存到工作区"));

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/executions/exec-1/commit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ accept_all: true }),
      }),
    );
    const headers = mockFetch.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get("Idempotency-Key")).toBeTruthy();
  });

  it("shows room links for saved outputs after commit", async () => {
    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByText("保存到工作区"));

    const docLink = await screen.findByRole("link", {
      name: "打开已保存的 综述初稿",
    });
    const docUrl = new URL(docLink.getAttribute("href")!, "https://example.test");
    expect(docUrl.pathname).toBe("/workspaces/ws-1");
    expect(docUrl.searchParams.get("room")).toBe("documents");
    expect(docUrl.searchParams.get("item_id")).toBe("doc-77");

    const libraryLink = screen.getByRole("link", {
      name: "打开已保存的 Deep Learning",
    });
    const libraryUrl = new URL(
      libraryLink.getAttribute("href")!,
      "https://example.test",
    );
    expect(libraryUrl.searchParams.get("room")).toBe("library");
    expect(libraryUrl.searchParams.get("item_id")).toBe("lib-88");

    const memoryLink = screen.getByRole("link", {
      name: "打开已保存的 研究主题：联邦学习大模型",
    });
    const memoryUrl = new URL(
      memoryLink.getAttribute("href")!,
      "https://example.test",
    );
    expect(memoryUrl.searchParams.get("room")).toBe("memory");
    expect(memoryUrl.searchParams.get("item_id")).toBe("mem-99");
  });

  it("renders DB-backed Prism review items with workspace navigation", () => {
    render(
      <ResultCard
        data={{
          ...SAMPLE_DATA,
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
        }}
        workspaceId="ws-1"
      />,
    );

    expect(screen.getByText("Intro rewrite")).toBeInTheDocument();
    expect(screen.getByText("sections/introduction.tex")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "预览待确认修改" }),
    ).toHaveAttribute(
      "href",
      "/workspaces/ws-1/prism?focus=file_changes&review_item_id=review-1&logical_key=section%3Aintroduction",
    );
  });

  it("renders sandbox artifact review items without Prism-specific copy or links", () => {
    render(
      <ResultCard
        data={{
          ...SAMPLE_DATA,
          review_items: [
            {
              id: "review-artifact-1",
              kind: "sandbox_artifact",
              status: "pending",
              title: "Accept sandbox artifact: sandbox_report",
              summary: "/workspace/reports/analysis.md",
              target: {
                kind: "sandbox_artifact",
                path: "/workspace/reports/analysis.md",
                artifact_kind: "sandbox_report",
                asset_id: "asset-1",
                sandbox_artifact_id: "artifact-1",
              },
              preview: {
                mode: "artifact",
                path: "/workspace/reports/analysis.md",
                mime_type: "text/markdown",
                content_hash: "sha256:analysis",
              },
            },
          ],
        }}
        workspaceId="ws-1"
      />,
    );

    expect(screen.getByText("产物有 1 项待确认保存")).toBeInTheDocument();
    expect(screen.getByText("Accept sandbox artifact: sandbox_report")).toBeInTheDocument();
    expect(screen.getByText("/workspace/reports/analysis.md")).toBeInTheDocument();
    expect(screen.queryByText(/Prism 有/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "预览待确认修改" }),
    ).not.toBeInTheDocument();
  });

  it("shows an inline error when saving fails", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: "Save failed" }),
    });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByText("保存到工作区"));

    expect(await screen.findByText("Save failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存到工作区" })).toBeInTheDocument();
  });

  it("calls commit with empty array on '暂不保存'", () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    fireEvent.click(screen.getByText("暂不保存"));

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/executions/exec-1/commit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ accepted_ids: [] }),
      }),
    );
  });
});
