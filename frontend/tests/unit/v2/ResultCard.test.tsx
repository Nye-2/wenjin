import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ResultCard } from "@/app/(workbench)/workspaces/[id]/components/ResultCard";

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
        },
      }),
  });
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
  ],
};

describe("ResultCard", () => {
  it("starts as a lightweight receipt and expands previews on demand", () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    expect(screen.getByText(/找到 15 篇相关文献/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看结果" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看结果" }));

    expect(screen.getAllByText("Deep Learning")).toHaveLength(2);
    expect(screen.getByText("Transformers")).toBeInTheDocument();
    expect(screen.getByText("综述初稿")).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
    expect(screen.getByText("保存到工作区")).toBeInTheDocument();
  });

  it("renders document detail preview when expanded", () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    fireEvent.click(screen.getByRole("button", { name: "查看结果" }));
    fireEvent.click(screen.getByText("综述初稿"));

    expect(screen.getByText("综述")).toBeInTheDocument();
    expect(screen.getByText("研究背景")).toBeInTheDocument();
  });

  it("calls commit with accept_all on '保存到工作区'", async () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    fireEvent.click(screen.getByRole("button", { name: "查看结果" }));
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

    fireEvent.click(screen.getByRole("button", { name: "查看结果" }));
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
    ).toHaveAttribute("href", "/workspaces/ws-1/prism?focus=file_changes");
  });

  it("shows an inline error when saving fails", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: "Save failed" }),
    });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "查看结果" }));
    fireEvent.click(screen.getByText("保存到工作区"));

    expect(await screen.findByText("Save failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存到工作区" })).toBeInTheDocument();
  });

  it("calls commit with selected ids on '仅保存勾选项'", () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    fireEvent.click(screen.getByRole("button", { name: "查看结果" }));
    fireEvent.click(screen.getByText("仅保存勾选项"));

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/executions/exec-1/commit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ accepted_ids: ["o1", "o2"] }),
      }),
    );
  });

  it("calls commit with empty array on '暂不保存'", () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    fireEvent.click(screen.getByRole("button", { name: "查看结果" }));
    fireEvent.click(screen.getByText("暂不保存"));

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/executions/exec-1/commit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ accepted_ids: [] }),
      }),
    );
  });

  it("allows toggling checkboxes before commit", () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    fireEvent.click(screen.getByRole("button", { name: "查看结果" }));
    const checkboxes = screen.getAllByRole("checkbox");

    fireEvent.click(checkboxes[0]);
    expect(checkboxes[0]).not.toBeChecked();

    fireEvent.click(checkboxes[2]);
    expect(checkboxes[2]).toBeChecked();
  });

  it("sends only manually checked ids after toggling", () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    fireEvent.click(screen.getByRole("button", { name: "查看结果" }));
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[2]);
    fireEvent.click(screen.getByText("仅保存勾选项"));

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/executions/exec-1/commit",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ accepted_ids: ["o2", "o3"] }),
      }),
    );
  });
});
