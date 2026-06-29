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
  rejected_ids: ["doc-1", "lib-1", "mem-1"],
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

const COMMITTED_STATE_DOC2 = {
  ...COMMITTED_STATE,
  accepted_ids: ["doc-2"],
  room_targets: {
    prism: [{ output_id: "doc-2", item_id: "saved-doc-2" }],
    library: [],
    memory: [],
    decisions: [],
    tasks: [],
  },
} as const;

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

function makeSecondCompletedRecord(): ExecutionRecord {
  const record = makeCompletedRecord();
  return {
    ...record,
    id: "exec-2",
    feature_id: "outline_followup",
    created_at: "2026-05-18T00:00:10Z",
    updated_at: "2026-05-18T00:00:15Z",
    started_at: "2026-05-18T00:00:10Z",
    completed_at: "2026-05-18T00:00:15Z",
    result: {
      task_report: {
        ...(record.result?.task_report as Record<string, unknown>),
        execution_id: "exec-2",
        narrative: "Second outline completed.",
        outputs: [
          {
            id: "doc-2",
            kind: "document",
            preview: "Second outline",
            default_checked: true,
            data: {
              name: "second-outline.md",
              mime_type: "text/markdown",
              doc_kind: "outline",
              content: "# Chapter 2",
            },
          },
        ],
      },
    },
  };
}

function withCommitState(
  record: ExecutionRecord,
  commitState:
    | typeof COMMITTED_STATE
    | typeof DISCARDED_STATE
    | typeof REVERTED_STATE
    | typeof COMMITTED_STATE_DOC2,
): ExecutionRecord {
  return {
    ...record,
    result: {
      ...(record.result ?? {}),
      commit_state: commitState,
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
          committed: { prism: 1 },
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
    localStorage.clear();
    useChatStoreV2.getState().reset();
    useChatStoreV2.setState({ sendMessage: originalSendMessage });
    useExecutionStore.getState().clear();
    useWorkbenchLayoutStore.getState().reset();
  });

  it("auto-commits completed outputs without a manual save button", async () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    const [, init] = mockFetch.mock.calls[0];
    expect(JSON.parse(init.body as string)).toEqual({
      accept_all: true,
    });
    expect(screen.queryByRole("button", { name: "全部保存" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "产物" })).not.toBeInTheDocument();
    expect(await screen.findByText("已写入工作区")).toBeInTheDocument();
  });

  it("does not auto-commit partial executions", async () => {
    useExecutionStore.getState().upsertExecution(makePartialRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.queryByRole("button", { name: "全部保存" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "保存已勾选" })).not.toBeInTheDocument();
    expect(screen.getByText("Some team members failed.")).toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("hydrates persisted commit_state as final after remount and tab switch", () => {
    useExecutionStore
      .getState()
      .upsertExecution(withCommitState(makeCompletedRecord(), DISCARDED_STATE));
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    const firstRender = render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.queryByRole("button", { name: "全部保存" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "暂不保存" })).not.toBeInTheDocument();
    expect(screen.getByText("已暂不保存")).toBeInTheDocument();
    expect(screen.queryByText("已写入工作区")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();

    firstRender.unmount();
    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "证据" }));
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getAllByText("只读").length).toBeGreaterThan(0);
  });

  it("patches returned commit_state into the execution store after commit", async () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toEqual(COMMITTED_STATE),
    );
    expect(
      await screen.findByRole("link", { name: "打开已保存的 Thesis outline" }),
    ).toBeInTheDocument();
  });

  it("undoes an auto-committed run from the run writeback status", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ commit_state: REVERTED_STATE }),
    });
    useExecutionStore
      .getState()
      .upsertExecution(withCommitState(makeCompletedRecord(), COMMITTED_STATE));
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "撤回本次保存" }));

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/executions/exec-1/commit/undo",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toEqual(REVERTED_STATE),
    );
    expect(screen.getByText("已撤回本次保存")).toBeInTheDocument();
  });

  it("does not finalize the selected run when a prior commit resolves after switching runs", async () => {
    let resolveCommit!: (payload: unknown) => void;
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        new Promise((resolve) => {
          resolveCommit = resolve;
        }),
    });
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useExecutionStore.getState().upsertExecution(makeSecondCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.getByText("Outline completed.")).toBeInTheDocument();
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ commit_state: COMMITTED_STATE_DOC2 }),
    });
    act(() => {
      useWorkbenchLayoutStore.getState().selectRun("exec-2");
    });
    expect(screen.getByText("Second outline completed.")).toBeInTheDocument();
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));

    await act(async () => {
      resolveCommit({ commit_state: COMMITTED_STATE });
    });

    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toEqual(COMMITTED_STATE),
    );
    expect(
      useExecutionStore.getState().executions.get("exec-2")?.result?.commit_state,
    ).toEqual(COMMITTED_STATE_DOC2);
    expect(useWorkbenchLayoutStore.getState().selectedRunId).toBe("exec-2");
    expect(screen.queryByRole("button", { name: "全部保存" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "打开已保存的 Thesis outline" }),
    ).not.toBeInTheDocument();
  });

  it("does not patch execution store or finalize when POST lacks backend commit_state", async () => {
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
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(
      await screen.findByText("保存状态同步失败，请刷新后重试"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试写入" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "打开已保存的 Thesis outline" })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toBeUndefined(),
    );
  });

  it("does not patch execution store when response commit_state is missing room_targets", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          commit_state: {
            status: COMMITTED_STATE.status,
            accepted_ids: COMMITTED_STATE.accepted_ids,
            rejected_ids: COMMITTED_STATE.rejected_ids,
            counts: COMMITTED_STATE.counts,
            committed_at: COMMITTED_STATE.committed_at,
          },
        }),
    });
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(
      await screen.findByText("保存状态同步失败，请刷新后重试"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试写入" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "打开已保存的 Thesis outline" })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toBeUndefined(),
    );
  });

  it("does not patch execution store when response commit_state has malformed room_targets", async () => {
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
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(
      await screen.findByText("保存状态同步失败，请刷新后重试"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试写入" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "打开已保存的 Thesis outline" })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toBeUndefined(),
    );
  });

  it("does not expose the product tab or memory snippets in the workbench chrome", () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.queryByRole("button", { name: "产物" })).not.toBeInTheDocument();
    expect(screen.getByText("Outline completed.")).toBeInTheDocument();
    expect(screen.queryByText("研究主题：联邦学习结合大模型微调")).not.toBeInTheDocument();
  });

  it("keeps result details in evidence without showing memory facts", () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("evidence");
    useWorkbenchLayoutStore.getState().setWorkbenchFullscreen(true);

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.getByRole("button", { name: "结果" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Thesis outline/ })).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /Federated Fine-tuning of Large Language Models/,
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("研究主题：联邦学习结合大模型微调")).not.toBeInTheDocument();
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
      expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("run"),
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

  it("omits raw node ids and input payload panes from run details by default", () => {
    useExecutionStore.getState().upsertExecution(makeTechnicalRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-technical");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.getAllByText("文献综合专家").length).toBeGreaterThan(0);
    expect(screen.getByText("文献综合")).toBeVisible();
    expect(screen.queryByText("输入预览")).not.toBeInTheDocument();
    expect(screen.queryByText("输出预览")).not.toBeInTheDocument();
    expect(screen.queryByText("联邦学习结合大模型")).not.toBeInTheDocument();
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

  it("routes super workflow capability picks into intake mode instead of direct launch", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({ sendMessage });

    render(
      <LiveWorkflowPanel
        workspaceId="ws-1"
        features={[
          {
            id: "software_copyright_application_pack",
            name: "软著申报材料包",
            description: "一步生成软著申报书、说明书、mock 代码和静态页面截图",
            icon: "file-text",
            stages: [],
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "软著申报材料包" }));

    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    const [, prompt, , options] = sendMessage.mock.calls[0];
    expect(prompt).toContain("先帮我梳理软著申报材料包的执行 Spec");
    expect(options.metadata.orchestration).toBeUndefined();
    expect(options.metadata.workbench_launch).toMatchObject({
      capability_id: "software_copyright_application_pack",
      mode: "intake",
    });
  });

  it("previews the latest intake spec and approves execution through chat launch metadata", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({
      sendMessage,
      messages: [
        {
          id: "msg-spec",
          role: "assistant",
          createdAt: "2026-06-29T00:00:00Z",
          blocks: [
            {
              kind: "tool_result",
              tool: "draft_intake_spec",
              status: "ready",
              output: {
                status: "ready",
                intake_spec: {
                  schema_version: "wenjin.intake_spec.v1",
                  spec_id: "intake-1",
                  revision: 1,
                  workspace_id: "ws-1",
                  workspace_type: "software_copyright",
                  capability_id: "software_copyright_application_pack",
                  title: "智慧排课系统软著申报 Spec",
                  status: "ready",
                  markdown:
                    "# 智慧排课系统软著申报 Spec\n\n生成申报书、说明书、mock 后端代码和静态前端截图。",
                  params: {
                    software_name: "智慧排课系统",
                    target_platform: "web",
                  },
                  missing_fields: [],
                  assumptions: ["按 Web 管理系统生成。"],
                },
              },
            },
          ],
        },
      ],
    });
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("spec");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.getByRole("heading", { name: "智慧排课系统软著申报 Spec" })).toBeVisible();
    expect(screen.getByText(/mock 后端代码和静态前端截图/)).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "同意，开始执行" }));

    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    const [, prompt, , options] = sendMessage.mock.calls[0];
    expect(prompt).toContain("同意并开始执行这份 Spec");
    expect(options.metadata.orchestration).toMatchObject({
      feature_id: "software_copyright_application_pack",
      params: {
        software_name: "智慧排课系统",
        target_platform: "web",
      },
    });
    expect(options.metadata.intake_spec_launch).toMatchObject({
      spec_id: "intake-1",
      revision: 1,
    });
  });

  it("keeps the right markdown preview synced to the latest workspace spec", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({
      sendMessage,
      messages: [
        {
          id: "msg-old",
          role: "assistant",
          createdAt: "2026-06-29T00:00:00Z",
          blocks: [
            {
              kind: "tool_result",
              tool: "draft_intake_spec",
              status: "ready",
              output: {
                status: "ready",
                intake_spec: {
                  schema_version: "wenjin.intake_spec.v1",
                  spec_id: "intake-old",
                  revision: 1,
                  workspace_id: "ws-1",
                  workspace_type: "software_copyright",
                  capability_id: "software_copyright_application_pack",
                  title: "旧版软著 Spec",
                  status: "ready",
                  markdown: "# 旧版软著 Spec\n\n旧版内容。",
                  params: { software_name: "旧系统" },
                  missing_fields: [],
                  assumptions: [],
                },
              },
            },
          ],
        },
        {
          id: "msg-new",
          role: "assistant",
          createdAt: "2026-06-29T00:02:00Z",
          blocks: [
            {
              kind: "tool_result",
              tool: "draft_intake_spec",
              status: "ready",
              output: {
                status: "ready",
                intake_spec: {
                  schema_version: "wenjin.intake_spec.v1",
                  spec_id: "intake-new",
                  revision: 3,
                  workspace_id: "ws-1",
                  workspace_type: "software_copyright",
                  capability_id: "software_copyright_application_pack",
                  title: "新版软著 Spec",
                  status: "ready",
                  markdown: "# 新版软著 Spec\n\n新版内容。",
                  params: { software_name: "新系统" },
                  missing_fields: [],
                  assumptions: [],
                },
              },
            },
          ],
        },
      ],
    });
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("spec");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.getByRole("heading", { name: "新版软著 Spec" })).toBeVisible();
    expect(screen.queryByText("旧版内容。")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "同意，开始执行" }));

    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    const [, , , options] = sendMessage.mock.calls[0];
    expect(options.metadata.orchestration.params).toEqual({ software_name: "新系统" });
    expect(options.metadata.intake_spec_launch).toMatchObject({
      spec_id: "intake-new",
      revision: 3,
    });
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
