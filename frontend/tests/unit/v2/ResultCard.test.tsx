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
        commit_state: VISIBLE_COMMITTED_STATE,
        room_targets: VISIBLE_COMMITTED_STATE.room_targets,
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

const NO_OUTPUT_DATA = {
  execution_id: "exec-1",
  capability_name: "设置更新",
  status: "completed" as const,
  duration_seconds: 4,
  narrative: "设置变更已准备好。",
  outputs: [],
};

const COMMITTED_STATE = {
  status: "committed",
  accepted_ids: ["o3"],
  rejected_ids: ["o1"],
  counts: {
    library: 1,
    prism: 1,
    memory: 1,
    decisions: 0,
    tasks: 0,
    sandbox: 0,
    settings: 0,
  },
  room_targets: {
    prism: [{ output_id: "o3", item_id: "doc-77" }],
    library: [{ output_id: "o1", item_id: "lib-88" }],
    memory: [{ output_id: "o4", item_id: "mem-99" }],
    decisions: [],
    tasks: [],
    sandbox: [],
    settings: [],
  },
  committed_at: "2026-06-20T00:00:00Z",
} as const;

const VISIBLE_COMMITTED_STATE = {
  status: "committed",
  accepted_ids: ["o1", "o2"],
  rejected_ids: ["o3", "o4"],
  counts: {
    library: 2,
    prism: 0,
    memory: 0,
    decisions: 0,
    tasks: 0,
    sandbox: 0,
    settings: 0,
  },
  room_targets: {
    prism: [],
    library: [
      { output_id: "o1", item_id: "lib-88" },
      { output_id: "o2", item_id: "lib-89" },
    ],
    memory: [],
    decisions: [],
    tasks: [],
    sandbox: [],
    settings: [],
  },
  committed_at: "2026-06-20T00:00:00Z",
} as const;

const DISCARDED_STATE = {
  status: "discarded",
  accepted_ids: [],
  rejected_ids: ["o1", "o2", "o3", "o4"],
  counts: {
    library: 0,
    prism: 0,
    memory: 0,
    decisions: 0,
    tasks: 0,
    sandbox: 0,
    settings: 0,
  },
  room_targets: {
    prism: [],
    library: [],
    memory: [],
    decisions: [],
    tasks: [],
    sandbox: [],
    settings: [],
  },
  committed_at: "2026-06-20T00:00:00Z",
} as const;

const REVERTED_STATE = {
  ...COMMITTED_STATE,
  status: "reverted",
  reverted_at: "2026-06-20T00:01:00Z",
  reverted_by: "user-1",
  revert_counts: {
    library: 1,
    prism: 1,
    memory: 1,
    decisions: 0,
    tasks: 0,
    sandbox: 0,
    settings: 0,
  },
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

function makeResultChangeSet(outputId: string) {
  return {
    execution_id: "exec-1",
    workspace_id: "ws-1",
    write_mode: "ask_workspace_write",
    summary: "Review concrete workspace writes.",
    created_at: "2026-06-20T00:00:00Z",
    units: [
      {
        id: "unit-doc-1",
        target: {
          room: "documents",
          object_type: "document",
          object_id: outputId,
          path: "review.md",
        },
        action: "write_document_draft",
        risk: "medium",
        risk_reasons: ["document draft changes require review"],
        default_apply_state: "staged",
        requires_confirmation: true,
        diff: { title: "Reviewed draft", summary: "Update draft" },
        provenance: { output_id: outputId },
        rollback: {},
      },
    ],
  };
}

function makeMaterializedSettingsChangeSet() {
  return {
    execution_id: "exec-1",
    workspace_id: "ws-1",
    write_mode: "ask_workspace_write",
    summary: "Review workspace setting updates.",
    created_at: "2026-06-20T00:00:00Z",
    units: [
      {
        id: "unit-settings-1",
        target: {
          room: "settings",
          object_type: "workspace_settings",
          object_id: "write_mode",
        },
        action: "update_workspace_settings",
        risk: "medium",
        risk_reasons: ["workspace write policy changes require review"],
        default_apply_state: "staged",
        requires_confirmation: true,
        diff: { title: "写入前询问", summary: "启用工作区写入确认" },
        provenance: { source_review_item_id: "settings-review-1" },
        rollback: {},
        materialization: {
          operation: "settings.update",
          payload: { write_mode: "ask_workspace_write" },
        },
      },
    ],
  };
}

describe("ResultCard", () => {
  it("renders a compact result package instead of a long in-chat list", () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    expect(screen.getByText(/找到 15 篇相关文献/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看运行" })).toBeInTheDocument();
    expect(screen.getByText("文献资料")).toBeInTheDocument();
    expect(screen.getByText("文档文件")).toBeInTheDocument();
    expect(screen.queryByText("研究主题：联邦学习大模型")).not.toBeInTheDocument();
    expect(screen.getByText("Deep Learning")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText("可保存结果，也可查看运行详情")).toBeInTheDocument();
    expect(screen.queryByText("保存到工作区")).not.toBeInTheDocument();
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

    expect(screen.getByText("图表文件")).toBeInTheDocument();
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

  it("opens the run surface for detailed result review", () => {
    useRunUiStore.getState().focusPreviewItem("stale-preview");
    render(<ResultCard data={SAMPLE_DATA} />);

    fireEvent.click(screen.getByRole("button", { name: "查看运行" }));

    expect(useWorkbenchLayoutStore.getState().selectedRunId).toBe("exec-1");
    expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("run");
    expect(useRunUiStore.getState().focusedPreviewItemId).toBeNull();
    expect(useWorkbenchLayoutStore.getState().isWorkbenchFullscreen).toBe(true);
  });

  it("opens the run preview surface when result card carries a preview item pointer", () => {
    render(<ResultCard data={{ ...SAMPLE_DATA, preview_item_id: "preview-1" }} />);

    fireEvent.click(screen.getByRole("button", { name: "查看运行" }));

    expect(useWorkbenchLayoutStore.getState().selectedRunId).toBe("exec-1");
    expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("run");
    expect(useRunUiStore.getState().focusedPreviewItemId).toBe("preview-1");
    expect(useWorkbenchLayoutStore.getState().isWorkbenchFullscreen).toBe(true);
  });

  it("does not commit when rendered outside a workspace surface", () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    expect(screen.queryByText("保存到工作区")).not.toBeInTheDocument();
    expect(screen.queryByText("暂不保存")).not.toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("does not auto-commit from the chat receipt when no run surface owns the execution", async () => {
    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    await Promise.resolve();

    expect(mockFetch).not.toHaveBeenCalled();
    expect(screen.getByText("可保存结果，也可查看运行详情")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存已确认结果（2 项）" })).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "打开已保存的 综述初稿" }),
    ).not.toBeInTheDocument();
  });

  it("manually saves default-selected chat receipt outputs", async () => {
    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "保存已确认结果（2 项）" }));

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/executions/exec-1/commit",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ accepted_ids: ["o1", "o2"] }),
        }),
      ),
    );
    expect(await screen.findByText("2 项结果已写入")).toBeInTheDocument();
    const libraryLink = screen.getByRole("link", { name: "打开已保存的 Deep Learning" });
    const libraryUrl = new URL(
      libraryLink.getAttribute("href")!,
      "https://example.test",
    );
    expect(libraryUrl.pathname).toBe("/workspaces/ws-1");
    expect(libraryUrl.searchParams.get("room")).toBe("library");
    expect(libraryUrl.searchParams.get("item_id")).toBe("lib-88");
    expect(
      screen.queryByRole("link", { name: "打开已保存的 综述初稿" }),
    ).not.toBeInTheDocument();
  });

  it("shows an inline error when manual chat receipt save has malformed commit_state", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          commit_state: {
            ...COMMITTED_STATE,
            room_targets: {
              ...COMMITTED_STATE.room_targets,
              prism: "bad",
            },
          },
        }),
    });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "保存已确认结果（2 项）" }));

    expect(
      await screen.findByText("保存状态同步失败，请刷新后重试"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试保存（2 项）" })).toBeInTheDocument();
  });

  it("does not show the old save button before ChangeSet units are accepted", () => {
    seedExecutionResult({ change_set: makeResultChangeSet("o3") });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    expect(screen.queryByRole("button", { name: /保存已确认结果/ })).not.toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("saves default-unchecked outputs after their ChangeSet units are accepted", async () => {
    seedExecutionResult({
      change_set: makeResultChangeSet("o3"),
      change_set_review_state: {
        schema_version: "wenjin.change_set.review_state.v1",
        accepted_unit_ids: ["unit-doc-1"],
        rejected_unit_ids: [],
        undone_unit_ids: [],
        updated_at: "2026-06-20T00:00:02Z",
      },
    });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          commit_state: COMMITTED_STATE,
        }),
    });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "保存已确认结果（1 项）" }));

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/executions/exec-1/commit",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ accepted_unit_ids: ["unit-doc-1"] }),
        }),
      ),
    );
  });

  it("saves accepted materialized ChangeSet units without historical output ids", async () => {
    seedExecutionResult({
      change_set: makeMaterializedSettingsChangeSet(),
      change_set_review_state: {
        schema_version: "wenjin.change_set.review_state.v1",
        accepted_unit_ids: ["unit-settings-1"],
        rejected_unit_ids: [],
        undone_unit_ids: [],
        updated_at: "2026-06-20T00:00:02Z",
      },
    });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          commit_state: {
            status: "committed",
            accepted_ids: ["unit-settings-1"],
            rejected_ids: [],
            counts: {
              library: 0,
              prism: 0,
              memory: 0,
              decisions: 0,
              tasks: 0,
              sandbox: 0,
              settings: 1,
            },
            room_targets: {
              prism: [],
              library: [],
              memory: [],
              decisions: [],
              tasks: [],
              sandbox: [],
              settings: [
                { output_id: "unit-settings-1", item_id: "ws-1" },
              ],
            },
            committed_at: "2026-06-20T00:00:00Z",
          },
        }),
    });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "保存已确认结果（1 项）" }));

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/executions/exec-1/commit",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ accepted_unit_ids: ["unit-settings-1"] }),
        }),
      ),
    );
  });

  it("saves accepted materialized ChangeSet units when the result card has no visible previews", async () => {
    seedExecutionResult({
      change_set: makeMaterializedSettingsChangeSet(),
      change_set_review_state: {
        schema_version: "wenjin.change_set.review_state.v1",
        accepted_unit_ids: ["unit-settings-1"],
        rejected_unit_ids: [],
        undone_unit_ids: [],
        updated_at: "2026-06-20T00:00:02Z",
      },
    });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          commit_state: {
            status: "committed",
            accepted_ids: ["unit-settings-1"],
            rejected_ids: [],
            counts: {
              library: 0,
              prism: 0,
              memory: 0,
              decisions: 0,
              tasks: 0,
              sandbox: 0,
              settings: 1,
            },
            room_targets: {
              prism: [],
              library: [],
              memory: [],
              decisions: [],
              tasks: [],
              sandbox: [],
              settings: [
                { output_id: "unit-settings-1", item_id: "ws-1" },
              ],
            },
            committed_at: "2026-06-20T00:00:00Z",
          },
        }),
    });

    render(<ResultCard data={NO_OUTPUT_DATA} workspaceId="ws-1" />);

    expect(screen.getByText("1 项结果待审核保存")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存已确认结果（1 项）" }));

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/executions/exec-1/commit",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ accepted_unit_ids: ["unit-settings-1"] }),
        }),
      ),
    );
    expect(await screen.findByText("1 项结果已写入")).toBeInTheDocument();
  });

  it("does not auto-commit when an execution record is already present", async () => {
    seedExecutionResult({});

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    expect(screen.getByText("可保存结果，也可查看运行详情")).toBeInTheDocument();
    await Promise.resolve();
    expect(mockFetch).not.toHaveBeenCalled();
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
    expect(screen.getByText("本次运行未完整完成，请先查看运行详情；需要保留的内容可继续在左侧对话中处理。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看运行" }));

    expect(mockFetch).not.toHaveBeenCalled();
    expect(useWorkbenchLayoutStore.getState().selectedRunId).toBe("exec-1");
    expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("run");
  });

  it("shows room links for persisted saved outputs", () => {
    seedExecutionResult({ commit_state: COMMITTED_STATE });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    const docLink = screen.getByRole("link", {
      name: "打开已保存的 综述初稿",
    });
    const docUrl = new URL(docLink.getAttribute("href")!, "https://example.test");
    expect(docUrl.pathname).toBe("/workspaces/ws-1/prism");
    expect(docUrl.searchParams.get("file_id")).toBe("doc-77");

    const libraryLink = screen.getByRole("link", {
      name: "打开已保存的 Deep Learning",
    });
    const libraryUrl = new URL(
      libraryLink.getAttribute("href")!,
      "https://example.test",
    );
    expect(libraryUrl.searchParams.get("room")).toBe("library");
    expect(libraryUrl.searchParams.get("item_id")).toBe("lib-88");

    expect(
      screen.queryByRole("link", {
        name: "打开已保存的 研究主题：联邦学习大模型",
      }),
    ).not.toBeInTheDocument();
  });

  it("renders persisted committed state from the execution store without POST", () => {
    seedExecutionResult({ commit_state: COMMITTED_STATE });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    expect(screen.getByText("3 项结果已写入")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "撤回本次保存" })).toBeInTheDocument();
    expect(screen.queryByText("保存到工作区")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "打开已保存的 综述初稿" }),
    ).toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("renders persisted discarded state from the execution store without POST", () => {
    seedExecutionResult({ commit_state: DISCARDED_STATE });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    expect(screen.getByText("已暂不保存")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "撤回本次保存" })).not.toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("uses POST undo commit_state to mark the card reverted", async () => {
    seedExecutionResult({ commit_state: COMMITTED_STATE });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          commit_state: REVERTED_STATE,
        }),
    });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "撤回本次保存" }));

    expect(await screen.findByText("已撤回本次保存")).toBeInTheDocument();
    expect(
      useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
    ).toEqual(REVERTED_STATE);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/executions/exec-1/commit/undo",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("does not fabricate or patch durable commit_state when undo lacks backend commit_state", async () => {
    seedExecutionResult({ commit_state: COMMITTED_STATE });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          committed: { prism: 1 },
          room_targets: {
            prism: [{ output_id: "o3", item_id: "doc-77" }],
            library: [],
            memory: [],
            decisions: [],
            tasks: [],
          },
        }),
    });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "撤回本次保存" }));

    expect(
      await screen.findByText("保存状态同步失败，请刷新后重试"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "撤回本次保存" })).not.toBeDisabled();
    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toEqual(COMMITTED_STATE),
    );
  });

  it("does not patch durable commit_state when undo response commit_state is missing counts", async () => {
    seedExecutionResult({ commit_state: COMMITTED_STATE });
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

    fireEvent.click(screen.getByRole("button", { name: "撤回本次保存" }));

    expect(
      await screen.findByText("保存状态同步失败，请刷新后重试"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "撤回本次保存" })).not.toBeDisabled();
    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toEqual(COMMITTED_STATE),
    );
  });

  it("does not patch durable commit_state when undo response commit_state has non-integer counts", async () => {
    seedExecutionResult({ commit_state: COMMITTED_STATE });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          commit_state: {
            ...COMMITTED_STATE,
            counts: { ...COMMITTED_STATE.counts, prism: 1.5 },
          },
        }),
    });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "撤回本次保存" }));

    expect(
      await screen.findByText("保存状态同步失败，请刷新后重试"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "撤回本次保存" })).not.toBeDisabled();
    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toEqual(COMMITTED_STATE),
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

    expect(screen.getByText("结果有 1 项可查看")).toBeInTheDocument();
    expect(screen.getByText("Accept sandbox artifact: sandbox_report")).toBeInTheDocument();
    expect(screen.getByText("/workspace/reports/analysis.md")).toBeInTheDocument();
    expect(screen.queryByText(/文档编辑器有/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "预览待确认修改" }),
    ).not.toBeInTheDocument();
  });

  it("shows an inline error when undo fails", async () => {
    seedExecutionResult({ commit_state: COMMITTED_STATE });
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: "Undo failed" }),
    });

    render(<ResultCard data={SAMPLE_DATA} workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "撤回本次保存" }));

    expect(await screen.findByText("Undo failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "撤回本次保存" })).toBeInTheDocument();
  });

  it("does not render discard controls on completed chat receipts", () => {
    render(<ResultCard data={SAMPLE_DATA} />);

    expect(screen.queryByText("暂不保存")).not.toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
