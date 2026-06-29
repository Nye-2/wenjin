import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompletedView } from "@/app/(workbench)/workspaces/[id]/components/CompletedView";
import type { ExecutionRecord } from "@/lib/api/types";
import { useExecutionStore } from "@/stores/execution-store";

const mockFetch = vi.fn();
global.fetch = mockFetch;

const COMMITTED_STATE = {
  status: "committed",
  accepted_ids: ["doc-1"],
  rejected_ids: [],
  counts: { library: 0, prism: 1, memory: 0, decisions: 0, tasks: 0 },
  room_targets: {
    prism: [{ output_id: "doc-1", item_id: "saved-doc-1" }],
    library: [],
    memory: [],
    decisions: [],
    tasks: [],
  },
  committed_at: "2026-06-20T00:00:00Z",
} as const;

const DISCARDED_STATE = {
  status: "discarded",
  accepted_ids: [],
  rejected_ids: ["doc-1"],
  counts: { library: 0, prism: 0, memory: 0, decisions: 0, tasks: 0 },
  room_targets: {
    prism: [],
    library: [],
    memory: [],
    decisions: [],
    tasks: [],
  },
  committed_at: "2026-06-20T00:00:00Z",
} as const;

const REVERTED_STATE = {
  ...COMMITTED_STATE,
  status: "reverted",
  reverted_at: "2026-06-20T00:01:00Z",
  reverted_by: "user-1",
  revert_counts: { library: 0, prism: 1, memory: 0, decisions: 0, tasks: 0 },
} as const;

const OUTLINE_TASK_REPORT = {
  execution_id: "exec-1",
  capability_id: "outline",
  status: "completed",
  narrative: "Outline completed.",
  outputs: [
    {
      id: "doc-1",
      kind: "document",
      preview: "Thesis outline",
      default_checked: true,
      data: {
        name: "outline.md",
        mime_type: "text/markdown",
        doc_kind: "outline",
        content: "# Chapter 1\n- Background",
      },
    },
  ],
};

describe("CompletedView", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          committed: { prism: 1, library: 0 },
          commit_state: COMMITTED_STATE,
          room_targets: {
            prism: [{ output_id: "doc-1", item_id: "saved-doc-1" }],
            library: [],
            memory: [],
            decisions: [],
            tasks: [],
          },
        }),
    });
    useExecutionStore.getState().clear();
  });

  it("renders TaskReport payloads from execution.completed", () => {
    render(
      <CompletedView
        result={{
          execution_id: "exec-1",
          capability_id: "lit_review",
          status: "failed_partial",
          duration_seconds: 8,
          narrative: "Found useful papers, with one source unavailable.",
          outputs: [
            {
              id: "paper-1",
              kind: "library_item",
              preview: "Smith et al. 2024",
              default_checked: true,
              data: { title: "Deep Learning", authors: ["Smith"] },
            },
          ],
          errors: [{ phase: "search", task: "semantic_scholar", error: "429" }],
        }}
      />,
    );

    expect(
      screen.getByText("Found useful papers, with one source unavailable."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Smith et al. 2024")).toHaveLength(2);
    expect(screen.getByText(/问题 1.*429/)).toBeInTheDocument();
  });

  it("renders nested task_report payloads as preview-first detail", () => {
    render(
      <CompletedView
        result={{
          task_report: {
            execution_id: "exec-1",
            capability_id: "outline",
            status: "completed",
            duration_seconds: 5,
            narrative: "Outline completed.",
            outputs: [
              {
                id: "doc-1",
                kind: "document",
                preview: "Thesis outline",
                default_checked: true,
                data: {
                  name: "outline.md",
                  mime_type: "text/markdown",
                  doc_kind: "outline",
                  content: "# Chapter 1\n- Background",
                },
              },
            ],
            errors: [],
          },
        }}
      />,
    );

    expect(screen.getByText("Outline completed.")).toBeInTheDocument();
    expect(screen.getAllByText("Thesis outline")).toHaveLength(2);
    expect(screen.getByText("Chapter 1")).toBeInTheDocument();
    expect(screen.getByText("Background")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "View full result" }),
    ).not.toBeInTheDocument();
  });

  it("builds resume links for supported execution next actions", () => {
    render(
      <CompletedView
        workspaceId="ws-1"
        featureId="framework_outline"
        executionId="exec-42"
        nextActions={[
          {
            action: "resume_execution",
            label: "继续执行",
          },
        ]}
      />,
    );

    const link = screen.getByRole("link", { name: "继续执行" });
    const url = new URL(link.getAttribute("href")!, "https://example.test");
    expect(url.pathname).toBe("/workspaces/ws-1");
    expect(url.searchParams.get("feature")).toBe("framework_outline");
    expect(url.searchParams.get("entry")).toBe("resume");
    expect(url.searchParams.get("execution_id")).toBe("exec-42");
  });

  it("keeps supported non-link actions visible as explicit badges", () => {
    render(
      <CompletedView
        nextActions={[
          {
            action: "continue_thread",
          },
        ]}
      />,
    );

    expect(screen.getByText("继续在对话中处理")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "继续在对话中处理" }),
    ).not.toBeInTheDocument();
  });

  it("routes open artifact actions into workspace rooms when no explicit url exists", () => {
    render(
      <CompletedView
        workspaceId="ws-1"
        nextActions={[
          {
            action: "open_artifact",
            artifact_kind: "document",
            artifact_id: "doc-7",
            item_id: "doc-1",
            title: "Research Paper Draft",
          },
        ]}
      />,
    );

    const link = screen.getByRole("link", { name: "查看结果" });
    const url = new URL(link.getAttribute("href")!, "https://example.test");
    expect(url.pathname).toBe("/workspaces/ws-1/prism");
    expect(url.searchParams.get("file_id")).toBe("doc-1");
  });

  it("routes Prism preview actions to the workspace Prism file-change focus", () => {
    render(
      <CompletedView
        workspaceId="ws-1"
        result={{
          data: {
            latex_project_id: "latex-1",
          },
        }}
        reviewItems={[
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
        ]}
        nextActions={[
          {
            action: "preview_prism_changes",
            label: "预览待确认修改",
            review_item_id: "review-1",
            logical_key: "section:introduction",
          },
        ]}
      />,
    );

    const link = screen.getByRole("link", { name: "预览待确认修改" });
    expect(link).toHaveAttribute(
      "href",
      "/workspaces/ws-1/prism?focus=file_changes&review_item_id=review-1&logical_key=section%3Aintroduction",
    );
    expect(screen.getByText("sections/introduction.tex")).toBeInTheDocument();
  });

  it("surfaces Prism review items from nested task_report when record-level review_items are absent", () => {
    render(
      <CompletedView
        workspaceId="ws-1"
        executionId="exec-1"
        result={{
          task_report: {
            execution_id: "exec-1",
            capability_id: "research_question_to_paper",
            status: "completed",
            narrative: "Manuscript draft completed.",
            outputs: [],
            review_items: [
              {
                id: "review-1",
                kind: "prism_file_change",
                logical_key: "project:main",
                status: "pending",
                title: "main.tex",
                summary: "feature_proposal",
                target: {
                  kind: "prism_file_change",
                  file_path: "main.tex",
                },
              },
            ],
          },
        }}
      />,
    );

    expect(screen.getByText("待确认修改")).toBeInTheDocument();
    expect(screen.getByText("main.tex")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "预览待确认修改" });
    expect(link).toHaveAttribute(
      "href",
      "/workspaces/ws-1/prism?focus=file_changes&review_item_id=review-1&logical_key=project%3Amain",
    );
  });

  it("commits staged previews from the execution panel and exposes saved room links", async () => {
    render(
      <CompletedView
        workspaceId="ws-1"
        executionId="exec-1"
        result={{
          task_report: {
            execution_id: "exec-1",
            capability_id: "outline",
            status: "completed",
            narrative: "Outline completed.",
            outputs: [
              {
                id: "doc-1",
                kind: "document",
                preview: "Thesis outline",
                default_checked: true,
                data: {
                  name: "outline.md",
                  mime_type: "text/markdown",
                  doc_kind: "outline",
                  content: "# Chapter 1\n- Background",
                },
              },
            ],
          },
        }}
      />,
    );

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/executions/exec-1/commit",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ accept_all: true }),
        }),
      ),
    );

    const savedLink = await screen.findByRole("link", { name: "打开已保存的 Thesis outline" });
    const url = new URL(savedLink.getAttribute("href")!, "https://example.test");
    expect(url.pathname).toBe("/workspaces/ws-1/prism");
    expect(url.searchParams.get("file_id")).toBe("saved-doc-1");
  });

  it("patches returned commit_state into the execution store after commit", async () => {
    const record: ExecutionRecord = {
      id: "exec-1",
      user_id: "user-1",
      workspace_id: "ws-1",
      execution_type: "capability",
      feature_id: "outline",
      status: "completed",
      params: {},
      result: { task_report: OUTLINE_TASK_REPORT },
      node_states: {},
      artifact_ids: [],
      next_actions: [],
      child_execution_ids: [],
      progress: 100,
      created_at: "2026-06-20T00:00:00Z",
      updated_at: "2026-06-20T00:00:00Z",
    };
    useExecutionStore.getState().upsertExecution(record);

    render(
      <CompletedView
        workspaceId="ws-1"
        executionId="exec-1"
        result={record.result}
      />,
    );

    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toEqual(COMMITTED_STATE),
    );
    expect(
      useExecutionStore.getState().executions.get("exec-1")?.result?.task_report,
    ).toEqual(OUTLINE_TASK_REPORT);
  });

  it("keeps partial execution previews read-only without manual save controls", async () => {
    render(
      <CompletedView
        workspaceId="ws-1"
        executionId="exec-1"
        result={{
          task_report: {
            execution_id: "exec-1",
            capability_id: "outline",
            status: "failed_partial",
            narrative: "Outline partially completed.",
            outputs: [
              {
                id: "doc-1",
                kind: "document",
                preview: "Thesis outline",
                default_checked: true,
                data: {
                  name: "outline.md",
                  mime_type: "text/markdown",
                  doc_kind: "outline",
                  content: "# Chapter 1\n- Background",
                },
              },
            ],
          },
        }}
      />,
    );

    expect(screen.queryByRole("button", { name: "保存到工作区" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "仅保存勾选项" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "暂不保存" })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText("本次运行未完整完成，候选结果只作为证据预览；需要继续处理时，请在左侧补充指令。")).toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("shows a save error inline when execution commit fails", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: "Commit failed" }),
    });

    render(
      <CompletedView
        workspaceId="ws-1"
        executionId="exec-1"
        result={{
          task_report: {
            execution_id: "exec-1",
            capability_id: "outline",
            status: "completed",
            narrative: "Outline completed.",
            outputs: [
              {
                id: "doc-1",
                kind: "document",
                preview: "Thesis outline",
                default_checked: true,
                data: {
                  name: "outline.md",
                  mime_type: "text/markdown",
                  doc_kind: "outline",
                  content: "# Chapter 1\n- Background",
                },
              },
            ],
          },
        }}
      />,
    );

    expect(await screen.findByText("Commit failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试写入" })).toBeInTheDocument();
  });

  it("does not finalize when POST succeeds without durable backend commit_state", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          committed: { prism: 1 },
          room_targets: {
            prism: [{ output_id: "doc-1", item_id: "saved-doc-1" }],
            library: [],
            memory: [],
            decisions: [],
            tasks: [],
          },
        }),
    });

    render(
      <CompletedView
        workspaceId="ws-1"
        executionId="exec-1"
        result={{ task_report: OUTLINE_TASK_REPORT }}
      />,
    );

    expect(
      await screen.findByText("保存状态同步失败，请刷新后重试"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试写入" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "打开已保存的 Thesis outline" })).not.toBeInTheDocument();
  });

  it("hydrates committed status and room links from result.commit_state", () => {
    render(
      <CompletedView
        workspaceId="ws-1"
        executionId="exec-1"
        result={{
          task_report: OUTLINE_TASK_REPORT,
          commit_state: COMMITTED_STATE,
        }}
      />,
    );

    expect(screen.getByText("已写入工作区")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存到工作区" })).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "打开已保存的 Thesis outline" }),
    ).toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("undoes committed status from the completed execution panel", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ commit_state: REVERTED_STATE }),
    });
    const record: ExecutionRecord = {
      id: "exec-1",
      user_id: "user-1",
      workspace_id: "ws-1",
      execution_type: "capability",
      feature_id: "outline",
      status: "completed",
      params: {},
      result: { task_report: OUTLINE_TASK_REPORT, commit_state: COMMITTED_STATE },
      node_states: {},
      artifact_ids: [],
      next_actions: [],
      child_execution_ids: [],
      progress: 100,
      created_at: "2026-06-20T00:00:00Z",
      updated_at: "2026-06-20T00:00:00Z",
    };
    useExecutionStore.getState().upsertExecution(record);

    render(
      <CompletedView
        workspaceId="ws-1"
        executionId="exec-1"
        result={record.result}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "撤回本次保存" }));

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/executions/exec-1/commit/undo",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(await screen.findByText("已撤回本次保存")).toBeInTheDocument();
    expect(
      useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
    ).toEqual(REVERTED_STATE);
  });

  it("hydrates discarded status from result.commit_state as a final not-saved state", () => {
    render(
      <CompletedView
        workspaceId="ws-1"
        executionId="exec-1"
        result={{
          task_report: OUTLINE_TASK_REPORT,
          commit_state: DISCARDED_STATE,
        }}
      />,
    );

    expect(screen.getByText("已暂不保存")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存到工作区" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "暂不保存" })).not.toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
