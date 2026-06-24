import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ResultCard } from "@/app/(workbench)/workspaces/[id]/components/ResultCard";
import type { ExecutionRecord } from "@/lib/api/types";
import { useExecutionStore } from "@/stores/execution-store";
import { useRunUiStore } from "@/stores/run-ui-store";
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
        commit_state: COMMITTED_STATE,
        room_targets: {
          documents: [{ output_id: "o3", item_id: "doc-77" }],
          library: [{ output_id: "o1", item_id: "lib-88" }],
          memory: [{ output_id: "o4", item_id: "mem-99" }],
        },
      }),
  });
  localStorage.clear();
  useExecutionStore.getState().clear();
  useWorkbenchLayoutStore.getState().reset();
  useRunUiStore.getState().reset();
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

const COMMITTED_STATE = {
  status: "committed",
  accepted_ids: ["o3"],
  rejected_ids: ["o1"],
  counts: { documents: 1, library: 1, memory: 1 },
  room_targets: {
    documents: [{ output_id: "o3", item_id: "doc-77" }],
    library: [{ output_id: "o1", item_id: "lib-88" }],
    memory: [{ output_id: "o4", item_id: "mem-99" }],
  },
  committed_at: "2026-06-20T00:00:00Z",
} as const;

const DISCARDED_STATE = {
  status: "discarded",
  accepted_ids: [],
  rejected_ids: ["o1", "o2", "o3", "o4"],
  counts: {},
  room_targets: {},
  committed_at: "2026-06-20T00:00:00Z",
} as const;

function seedExecutionResult(result: Record<string, unknown>) {
  const record: ExecutionRecord = {
    id: "exec-1",
    user_id: "user-1",
    workspace_id: "ws-1",
    execution_type: "capability",
    feature_id: "lit_search",
    status: "completed",
    params: {},
    result,
    node_states: {},
    artifact_ids: [],
    next_actions: [],
    child_execution_ids: [],
    progress: 100,
    created_at: "2026-06-20T00:00:00Z",
    updated_at: "2026-06-20T00:00:00Z",
  };
  useExecutionStore.getState().upsertExecution(record);
}

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

  it("sanitizes raw runtime narrative before rendering the chat result card", () => {
    render(
      <ResultCard
        data={{
          ...SAMPLE_DATA,
          narrative:
            '{"stdout":"raw narrative should stay hidden","ref":"/workspace/outputs/harness/exec-1/result.json"}',
        }}
      />,
    );

    expect(screen.getByText("运行结果已生成。")).toBeInTheDocument();
    expect(screen.queryByText(/stdout/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw narrative should stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/workspace\/outputs\/harness/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\{/)).not.toBeInTheDocument();
  });

  it("renders figure outputs with a visual placeholder and figure summary", () => {
    render(
      <ResultCard
        data={{
          ...SAMPLE_DATA,
          capability_name: "图表生成",
          outputs: [
            {
              id: "fig-1",
              kind: "figure",
              preview: "Accuracy trend",
              default_checked: true,
              data: {
                title: "Accuracy trend",
                primary_path: "/workspace/outputs/figures/run-1/figure.png",
                caption: "Validation accuracy improved across the final three epochs.",
                strategy: "matplotlib_line_chart",
                figure_type: "line",
                provenance: "sandbox",
              },
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("图表产物")).toBeInTheDocument();
    expect(screen.getByText("图表")).toBeInTheDocument();
    expect(screen.getByText("Accuracy trend")).toBeInTheDocument();
    expect(
      screen.getByText("Validation accuracy improved across the final three epochs."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/matplotlib_line_chart/)).not.toBeInTheDocument();
    expect(screen.queryByText(/strategy:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/figure_type:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/provenance:/)).not.toBeInTheDocument();
  });

  it("opens the workbench review surface for detailed result review", () => {
    useRunUiStore.getState().focusPreviewItem("stale-preview");
    render(<ResultCard data={SAMPLE_DATA} />);

    fireEvent.click(screen.getByRole("button", { name: "查看详情" }));

    expect(useWorkbenchLayoutStore.getState().selectedRunId).toBe("exec-1");
    expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("review");
    expect(useRunUiStore.getState().focusedPreviewItemId).toBeNull();
    expect(useWorkbenchLayoutStore.getState().isWorkbenchFullscreen).toBe(true);
  });

  it("opens the run preview surface when result card carries a preview item pointer", () => {
    render(<ResultCard data={{ ...SAMPLE_DATA, preview_item_id: "preview-1" }} />);

    fireEvent.click(screen.getByRole("button", { name: "查看详情" }));

    expect(useWorkbenchLayoutStore.getState().selectedRunId).toBe("exec-1");
    expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("run");
    expect(useRunUiStore.getState().focusedPreviewItemId).toBe("preview-1");
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

  it("requires manual review before saving partial execution outputs", () => {
    render(
      <ResultCard
        data={{
          ...SAMPLE_DATA,
          status: "failed_partial",
          narrative: "未能完成全部步骤。",
          outputs: SAMPLE_DATA.outputs.map((output) => ({
            ...output,
            default_checked: true,
          })),
        }}
      />,
    );

    expect(screen.queryByRole("button", { name: "保存到工作区" })).not.toBeInTheDocument();
    expect(screen.getByText("本次运行未完整完成，候选结果需要先查看详情后再决定是否保存。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看候选项" }));

    expect(mockFetch).not.toHaveBeenCalled();
    expect(useWorkbenchLayoutStore.getState().selectedRunId).toBe("exec-1");
    expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("review");
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

  it("renders persisted committed state from the execution store without POST", () => {
    seedExecutionResult({ commit_state: COMMITTED_STATE });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    const saveButton = screen.getByRole("button", { name: "已保存到工作区" });
    expect(saveButton).toBeDisabled();
    expect(screen.getByRole("button", { name: "暂不保存" })).toBeDisabled();
    expect(
      screen.getByRole("link", { name: "打开已保存的 综述初稿" }),
    ).toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("renders persisted discarded state from the execution store without POST", () => {
    seedExecutionResult({ commit_state: DISCARDED_STATE });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    const finalButtons = screen.getAllByRole("button", { name: "已暂不保存" });
    expect(finalButtons.length).toBeGreaterThan(0);
    finalButtons.forEach((button) => expect(button).toBeDisabled());
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("uses POST commit_state to finalize the card, patch the execution store, and show links", async () => {
    seedExecutionResult({ task_report: { execution_id: "exec-1" } });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          commit_state: COMMITTED_STATE,
        }),
    });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "保存到工作区" }));

    expect(
      await screen.findByRole("link", { name: "打开已保存的 综述初稿" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "已保存到工作区" })).toBeDisabled();
    expect(
      useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
    ).toEqual(COMMITTED_STATE);
  });

  it("does not fabricate or patch durable commit_state when POST lacks backend commit_state", async () => {
    seedExecutionResult({ task_report: { execution_id: "exec-1" } });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          committed: { documents: 1 },
          room_targets: {
            documents: [{ output_id: "o3", item_id: "doc-77" }],
          },
        }),
    });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "保存到工作区" }));

    expect(
      await screen.findByText("保存状态同步失败，请刷新后重试"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存到工作区" })).not.toBeDisabled();
    expect(screen.queryByRole("link", { name: "打开已保存的 综述初稿" })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toBeUndefined(),
    );
  });

  it("does not patch durable commit_state when response commit_state is missing counts", async () => {
    seedExecutionResult({ task_report: { execution_id: "exec-1" } });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          commit_state: {
            status: COMMITTED_STATE.status,
            accepted_ids: COMMITTED_STATE.accepted_ids,
            rejected_ids: COMMITTED_STATE.rejected_ids,
            room_targets: COMMITTED_STATE.room_targets,
            committed_at: COMMITTED_STATE.committed_at,
          },
        }),
    });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "保存到工作区" }));

    expect(
      await screen.findByText("保存状态同步失败，请刷新后重试"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存到工作区" })).not.toBeDisabled();
    expect(screen.queryByRole("link", { name: "打开已保存的 综述初稿" })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toBeUndefined(),
    );
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
