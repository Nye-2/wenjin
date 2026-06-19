import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

function makePartialRecord(): ExecutionRecord {
  const record = makeCompletedRecord();
  return {
    ...record,
    status: "failed_partial",
    result: {
      task_report: {
        ...(record.result?.task_report as Record<string, unknown>),
        status: "failed_partial",
        narrative: "Some team members failed.",
      },
    },
  };
}

function makeTeamRunningRecord(): ExecutionRecord {
  return {
    ...makeRunningRecord(),
    id: "exec-team",
    feature_id: "team_research",
    display_name: "团队调研",
    graph_structure: {
      mode: "team_kernel",
      nodes: [],
      edges: [],
    },
    node_states: {
      "research_scholar.v1__1": {
        status: "completed",
        node_type: "agent_invocation",
        label: "文献专家",
        node_metadata: {
          team: true,
          template_id: "research_scholar.v1",
          display_name: "文献专家",
          effective_tools: ["web_search", "library_read"],
          effective_skills: ["literature_search.v1"],
          harness: {
            expert_preview_items: [
              {
                preview_item_id: "saved-preview-1",
                title: "候选文献预览",
                kind: "literature_list",
                summary: "已经保存到资料库的候选文献摘要。",
                status: "saved",
                created_at: "2026-06-13T00:00:00Z",
              },
            ],
          },
        },
      },
      "critical_reviewer.v1__1": {
        status: "running",
        node_type: "agent_invocation",
        label: "质量审稿人",
        node_metadata: {
          team: true,
          template_id: "critical_reviewer.v1",
          display_name: "质量审稿人",
          effective_tools: ["library_read"],
          effective_skills: ["critical_review.v1"],
        },
      },
      "literature_synthesizer.v1__1": {
        status: "pending",
        node_type: "agent_invocation",
        label: "文献综合专家",
        node_metadata: {
          team: true,
          template_id: "literature_synthesizer.v1",
          display_name: "文献综合专家",
          effective_tools: ["library_read"],
          effective_skills: ["evidence_synthesis.v1"],
        },
      },
    },
    runtime_state: {
      quality_gates: [
        {
          gate_id: "evidence_traceability",
          status: "warning",
          severity: "medium",
          next_action: "revise_evidence_map",
        },
      ],
    },
  };
}

function makeTechnicalRunningRecord(): ExecutionRecord {
  return {
    ...makeRunningRecord(),
    id: "exec-technical",
    feature_id: "sci_literature_positioning",
    display_name: "文献定位与创新点",
    graph_structure: {
      nodes: [
        {
          id: "step_02_literature_synthesizer",
          type: "agent_invocation",
          phase: "synthesis",
          task: "literature_synthesizer",
        },
      ],
      edges: [],
    },
    node_states: {
      step_02_literature_synthesizer: {
        status: "running",
        node_type: "agent_invocation",
        thinking: "正在把检索结果整理成主题矩阵。",
        input: {
          task_focus: "把检索结果和材料综合为主题矩阵、gap、可引用论断和后续写作素材。",
          raw_message: "联邦学习结合大模型",
        },
      },
    },
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
    fireEvent.click(screen.getByRole("button", { name: "全部保存" }));

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

  it("does not accept all outputs from partial executions", async () => {
    useExecutionStore.getState().upsertExecution(makePartialRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("review");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.queryByRole("button", { name: "全部保存" })).not.toBeInTheDocument();
    expect(screen.getByText("本次运行未完整完成，默认不会全选候选项。请逐项预览后保存已勾选内容。")).toBeInTheDocument();

    const outlineRow = screen
      .getByRole("button", { name: /Thesis outline/ })
      .closest("div");
    expect(outlineRow).not.toBeNull();
    fireEvent.click(within(outlineRow as HTMLElement).getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "保存已勾选" }));

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    const [, init] = mockFetch.mock.calls[0];
    expect(JSON.parse(init.body as string)).toEqual({
      accepted_ids: ["doc-1"],
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

  it("renders实名团队成员和质量门摘要 for team-kernel runs", () => {
    useExecutionStore.getState().upsertExecution(makeTeamRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-team");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    const teamRegion = screen.getByRole("region", { name: "执行团队" });
    expect(within(teamRegion).getByText("文献专家")).toBeInTheDocument();
    expect(within(teamRegion).getByText("质量审稿人")).toBeInTheDocument();
    expect(within(teamRegion).getAllByText("能力已就绪").length).toBeGreaterThan(0);
    expect(within(teamRegion).getByText("证据可追溯")).toBeInTheDocument();
    expect(within(teamRegion).getByText("提醒")).toBeInTheDocument();
  });

  it("leaves run-level status to the workspace chrome and keeps interrupt action once", () => {
    useExecutionStore.getState().upsertExecution(makeRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.queryByText("运行中")).not.toBeInTheDocument();
    expect(screen.getAllByText("中断并补充")).toHaveLength(1);
  });

  it("uses distinct member-level status labels in team runs", () => {
    useExecutionStore.getState().upsertExecution(makeTeamRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-team");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    const teamRegion = screen.getByRole("region", { name: "执行团队" });
    expect(visibleOutsideClosedDetails("运行中")).toHaveLength(0);
    expect(within(teamRegion).getByText("处理中")).toBeInTheDocument();
    expect(within(teamRegion).getByText("待处理")).toBeInTheDocument();
  });

  it("labels saved expert previews as saved instead of draft", () => {
    useExecutionStore.getState().upsertExecution(makeTeamRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-team");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    const teamRegion = screen.getByRole("region", { name: "执行团队" });
    fireEvent.click(within(teamRegion).getByRole("button", { name: "打开预览" }));

    const previewRegion = screen.getByRole("region", { name: "结果预览" });
    expect(within(previewRegion).getByText("已保存")).toBeInTheDocument();
    expect(within(previewRegion).queryByText("草稿")).not.toBeInTheDocument();
  });

  it("keeps raw node ids and input payloads behind run details by default", () => {
    useExecutionStore.getState().upsertExecution(makeTechnicalRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-technical");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.getAllByText("文献综合专家").length).toBeGreaterThan(0);
    expect(screen.getByText("文献综合")).toBeVisible();
    expect(screen.getByText("输入预览")).not.toBeVisible();
    for (const element of screen.getAllByText(/literature_synthesizer/)) {
      expect(element).not.toBeVisible();
    }
  });

  it("routes direct capability picks through canonical orchestration metadata", async () => {
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

    fireEvent.click(screen.getByRole("button", { name: "文献定位与创新点" }));

    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    const [, prompt, , options] = sendMessage.mock.calls[0];
    expect(prompt).toContain("我想使用「文献定位与创新点」能力。");
    expect(prompt).toContain("请先确认启动所需的具体研究主题、材料或目标");
    expect(options.metadata.orchestration.feature_id).toBe("sci_literature_positioning");
  });

  it("keeps the idle overview focused on task launch instead of empty dashboard controls", () => {
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

    expect(screen.queryByRole("button", { name: "中断并补充" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "文献定位与创新点" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: /建立相关工作、gap 和 contribution positioning/,
      }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("正在处理")).not.toBeInTheDocument();
    expect(screen.queryByText("还没有运行记录")).not.toBeInTheDocument();
  });
});

function visibleOutsideClosedDetails(text: string) {
  return screen.queryAllByText(text).filter((element) => {
    const details = element.closest("details");
    return !details || details.open;
  });
}
