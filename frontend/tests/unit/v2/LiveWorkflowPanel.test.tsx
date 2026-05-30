import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import { useExecutionStore } from "@/stores/execution-store";
import { useChatStoreV2 } from "@/stores/chat-store";
import { useWorkbenchLayoutStore } from "@/stores/workbench-layout-store";
import { LiveWorkflowPanel } from "@/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel";

const mockFetch = vi.fn();
global.fetch = mockFetch;
const originalSendMessage = useChatStoreV2.getState().sendMessage;

function makeCompletedRecord(): ExecutionRecord {
  return {
    id: "exec-1",
    user_id: "user-1",
    workspace_id: "ws-1",
    execution_type: "capability",
    feature_id: "outline",
    status: "completed",
    params: {},
    node_states: {},
    artifact_ids: [],
    next_actions: [],
    child_execution_ids: [],
    progress: 100,
    created_at: "2026-05-18T00:00:00Z",
    updated_at: "2026-05-18T00:00:05Z",
    started_at: "2026-05-18T00:00:00Z",
    completed_at: "2026-05-18T00:00:05Z",
    result: {
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
              content: "# Chapter 1",
            },
          },
          {
            id: "lib-1",
            kind: "library_item",
            preview: "Smith et al. 2025",
            default_checked: true,
            data: {
              title: "Federated Fine-tuning of Large Language Models",
              authors: ["Smith"],
              year: 2025,
              abstract: "A study about federated LLM adaptation.",
            },
          },
          {
            id: "mem-1",
            kind: "memory_fact",
            preview: "研究主题：联邦学习结合大模型微调",
            default_checked: true,
            data: {
              category: "context",
              content: "研究主题：联邦学习结合大模型微调",
            },
          },
        ],
      },
    },
  };
}

function makeRunningRecord(): ExecutionRecord {
  return {
    ...makeCompletedRecord(),
    status: "running",
    progress: 35,
    completed_at: null,
    result: null,
  };
}

describe("LiveWorkflowPanel", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          committed: { documents: 1 },
          room_targets: {
            documents: [{ output_id: "doc-1", item_id: "saved-doc-1" }],
          },
        }),
    });
    localStorage.clear();
    useChatStoreV2.getState().reset();
    useChatStoreV2.setState({ sendMessage: originalSendMessage });
    useExecutionStore.getState().clear();
    useWorkbenchLayoutStore.getState().reset();
  });

  it("commits staged edits as output_overrides", async () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("review");
    useWorkbenchLayoutStore.getState().setWorkbenchFullscreen(true);

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    fireEvent.change(screen.getByLabelText("文件名"), {
      target: { value: "edited-outline.md" },
    });
    fireEvent.click(screen.getByRole("button", { name: "全部接受" }));

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    const [, init] = mockFetch.mock.calls[0];
    expect(JSON.parse(init.body as string)).toEqual({
      accept_all: true,
      output_overrides: {
        "doc-1": {
          data: { name: "edited-outline.md" },
        },
      },
    });
  });

  it("uses room-specific labels in the review inbox", () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("review");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.getAllByText("文档产物").length).toBeGreaterThan(0);
    expect(screen.getAllByText("文献资料").length).toBeGreaterThan(0);
    expect(screen.getAllByText("记忆片段").length).toBeGreaterThan(0);
  });

  it("renders review as a list-detail surface", () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("review");
    useWorkbenchLayoutStore.getState().setWorkbenchFullscreen(true);

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(
      screen.getByRole("region", { name: "候选结果列表" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "候选结果详情" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Thesis outline").length).toBeGreaterThan(1);

    fireEvent.click(
      screen.getByRole("button", {
        name: /Federated Fine-tuning of Large Language Models/,
      }),
    );

    expect(
      screen.getAllByText("Federated Fine-tuning of Large Language Models").length,
    ).toBeGreaterThan(1);
    expect(
      screen.getAllByText("A study about federated LLM adaptation.").length,
    ).toBeGreaterThan(1);
  });

  it("filters review candidates by result room without losing the detail surface", () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("review");
    useWorkbenchLayoutStore.getState().setWorkbenchFullscreen(true);

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "筛选文献资料" }));

    expect(
      screen.queryByRole("button", { name: /Thesis outline/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /Federated Fine-tuning of Large Language Models/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "候选结果详情" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("A study about federated LLM adaptation.").length,
    ).toBeGreaterThan(1);
  });

  it("keeps review lightweight outside fullscreen and opens detail mode on candidate click", () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("review");
    useWorkbenchLayoutStore.getState().setWorkbenchFullscreen(false);

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(
      screen.getByRole("region", { name: "候选结果列表" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "候选结果详情" }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: /Federated Fine-tuning of Large Language Models/,
      }),
    );

    expect(useWorkbenchLayoutStore.getState().isWorkbenchFullscreen).toBe(true);
    expect(
      screen.getByRole("region", { name: "候选结果详情" }),
    ).toBeInTheDocument();
  });

  it("auto-follows completed runs after temporary tab navigation", async () => {
    useExecutionStore.getState().upsertExecution(makeRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "证据" }));
    expect(screen.queryByRole("button", { name: /自动聚焦/ })).not.toBeInTheDocument();

    act(() => {
      useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    });

    await waitFor(() =>
      expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("review"),
    );
  });

  it("asks for a concrete topic before direct capability launch can run broad research", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({ sendMessage });

    render(
      <LiveWorkflowPanel
        workspaceId="ws-1"
        features={[
          {
            id: "sci_literature_positioning",
            name: "文献定位与创新点",
            description: "建立相关工作、gap 和 contribution positioning",
            icon: "book-open",
            stages: [],
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /文献定位与创新点/ }));

    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    const [, prompt] = sendMessage.mock.calls[0];
    expect(prompt).toContain("缺少具体研究主题");
    expect(prompt).toContain("先向用户确认");
  });
});
