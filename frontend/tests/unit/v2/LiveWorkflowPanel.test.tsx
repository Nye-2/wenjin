import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import { useExecutionStore } from "@/stores/execution-store";
import { useChatStoreV2 } from "@/stores/chat-store";
import { useRunUiStore } from "@/stores/run-ui-store";
import { useWorkbenchLayoutStore } from "@/stores/workbench-layout-store";
import { LiveWorkflowPanel } from "@/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel";

const mockFetch = vi.fn();
global.fetch = mockFetch;
const originalSendMessage = useChatStoreV2.getState().sendMessage;

const COMMITTED_STATE = {
  status: "committed",
  accepted_ids: ["doc-1"],
  rejected_ids: [],
  counts: {
    library: 0,
    prism: 1,
    memory: 0,
    decisions: 0,
    tasks: 0,
    sandbox: 0,
    settings: 0,
  },
  room_targets: {
    prism: [{ output_id: "doc-1", item_id: "saved-doc-1" }],
    library: [],
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
  rejected_ids: ["doc-1", "lib-1", "mem-1"],
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
    library: 0,
    prism: 1,
    memory: 0,
    decisions: 0,
    tasks: 0,
    sandbox: 0,
    settings: 0,
  },
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
    sandbox: [],
    settings: [],
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

function makeChangeSetCompletedRecord(): ExecutionRecord {
  const record = makeCompletedRecord();
  return {
    ...record,
    result: {
      ...(record.result ?? {}),
      change_set: makeReviewChangeSet(),
    },
  };
}

function makeReviewedChangeSetCompletedRecord(): ExecutionRecord {
  const record = makeChangeSetCompletedRecord();
  return {
    ...record,
    result: {
      ...(record.result ?? {}),
      change_set_review_state: {
        schema_version: "wenjin.change_set.review_state.v1",
        accepted_unit_ids: ["unit-doc-1"],
        rejected_unit_ids: ["unit-lib-1"],
        undone_unit_ids: [],
        updated_at: "2026-06-20T00:00:02Z",
      },
    },
  };
}

function makeDraftAppliedChangeSetCompletedRecord(): ExecutionRecord {
  const record = makeCompletedRecord();
  return {
    ...record,
    result: {
      ...(record.result ?? {}),
      change_set: {
        execution_id: "exec-1",
        workspace_id: "ws-1",
        write_mode: "auto_draft",
        summary: "Draft was applied automatically.",
        created_at: "2026-06-20T00:00:00Z",
        units: [
          {
            id: "unit-doc-1",
            target: {
              room: "documents",
              object_type: "document",
              object_id: "doc-1",
              path: "outline.md",
            },
            action: "write_document_draft",
            risk: "low",
            risk_reasons: [],
            default_apply_state: "draft_applied",
            requires_confirmation: false,
            diff: { title: "Thesis outline", summary: "Draft applied" },
            provenance: { output_id: "doc-1" },
            rollback: {},
          },
        ],
      },
    },
  };
}

function makeReviewChangeSet() {
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
          object_id: "doc-1",
          path: "outline.md",
        },
        action: "write_document_draft",
        risk: "medium",
        risk_reasons: ["document draft changes require review"],
        default_apply_state: "staged",
        requires_confirmation: true,
        diff: { title: "Thesis outline", summary: "Update outline" },
        provenance: { output_id: "doc-1" },
        rollback: {},
      },
      {
        id: "unit-lib-1",
        target: {
          room: "library",
          object_type: "library_item",
          object_id: "lib-1",
        },
        action: "add_library_item",
        risk: "high",
        risk_reasons: ["citation evidence requires manual confirmation"],
        default_apply_state: "blocked",
        requires_confirmation: true,
        diff: {
          title: "Federated Fine-tuning of Large Language Models",
          summary: "Add source candidate",
        },
        provenance: { output_id: "lib-1" },
        rollback: {},
      },
    ],
  };
}

function makeAcceptedChangeSetResponse(unitIds: string[]) {
  const reviewState = {
    schema_version: "wenjin.change_set.review_state.v1",
    accepted_unit_ids: unitIds,
    rejected_unit_ids: [],
    undone_unit_ids: [],
    updated_at: "2026-06-20T00:00:02Z",
  };
  const accepted = new Set(unitIds);
  return {
    change_set: makeReviewChangeSet(),
    review_state: reviewState,
    unit_states: makeReviewChangeSet().units.map((unit) => ({
      unit_id: unit.id,
      default_apply_state: unit.default_apply_state,
      state: accepted.has(unit.id) ? "accepted" : unit.default_apply_state,
    })),
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

function makeHiddenOnlyCompletedRecord(): ExecutionRecord {
  const record = makeCompletedRecord();
  return {
    ...record,
    id: "exec-hidden",
    result: {
      task_report: {
        ...(record.result?.task_report as Record<string, unknown>),
        execution_id: "exec-hidden",
        narrative: "Memory-only update completed.",
        outputs: [
          {
            id: "mem-only-1",
            kind: "memory_fact",
            preview: "隐藏背景记忆",
            default_checked: true,
            data: {
              category: "context",
              content: "隐藏背景记忆",
            },
          },
        ],
      },
    },
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

function makeEvidenceMissionRecord(): ExecutionRecord {
  return {
    ...makeRunningRecord(),
    id: "exec-evidence",
    display_name: "证据整理",
    graph_structure: {
      mode: "team_kernel",
      nodes: [
        {
          id: "scholar",
          type: "agent_invocation",
          phase: "research",
          task: "research_scholar",
          label: "文献专家",
        },
      ],
      edges: [],
    },
    node_states: {
      scholar: {
        status: "running",
        node_type: "agent_invocation",
        label: "文献专家",
        output: {
          evidence_packet: [
            { evidence_id: "ev-1", verification_status: "verified" },
            { evidence_id: "ev-2", verification_status: "found" },
          ],
          claims: [
            {
              id: "claim-1",
              claim: "模型性能提升来自检索到的两篇论文。",
              status: "verified",
              evidence_refs: ["ev-1"],
            },
          ],
        },
      },
    },
    runtime_state: {
      research_state: {
        schema_version: "wenjin.research_state.v1",
        goal: "整理当前任务的证据与结论。",
        open_questions: [],
        next_actions: ["补充第二条来源"],
        evidence_packet: [
          { evidence_id: "ev-1", verification_status: "verified" },
          { evidence_id: "ev-2", verification_status: "found" },
        ],
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
    useRunUiStore.getState().reset();
    useWorkbenchLayoutStore.getState().reset();
  });

  it("does not auto-commit completed outputs before review", async () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    await screen.findByRole("heading", { name: "复核与保存" });
    await act(async () => {
      await Promise.resolve();
    });
    expect(mockFetch).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "全部保存" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "产物" })).not.toBeInTheDocument();
    expect(screen.getByText("待复核保存")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存到工作区（2 项）" })).toBeInTheDocument();
  });

  it("shows a visible review tab with the pending review count", async () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    const reviewTab = await screen.findByRole("button", { name: "复核" });
    expect(within(reviewTab).getByText("2")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "复核与保存" })).toBeVisible();
    expect(screen.getByText("2 项内容待复核。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存到工作区（2 项）" })).toBeInTheDocument();
    expect(screen.getAllByText("Thesis outline").length).toBeGreaterThan(0);
    expect(screen.queryByText("研究主题：联邦学习结合大模型微调")).not.toBeInTheDocument();
  });

  it("hides the evidence and review tabs when there is nothing to show", () => {
    useExecutionStore.getState().upsertExecution(makeRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.queryByRole("button", { name: "证据" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "复核" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "进展" })).toBeInTheDocument();
  });

  it("keeps the fullscreen control accessible from the mission header", () => {
    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    const fullscreenButton = screen.getByRole("button", { name: "右侧全屏" });
    expect(fullscreenButton).toBeInTheDocument();

    fireEvent.click(fullscreenButton);

    expect(useWorkbenchLayoutStore.getState().isWorkbenchFullscreen).toBe(true);
    expect(screen.getByRole("button", { name: "退出全屏" })).toBeInTheDocument();
  });

  it("keeps history as a secondary action when no mission is active or explicitly selected", async () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    await waitFor(() =>
      expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("review"),
    );
    expect(screen.queryByRole("button", { name: "进展" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看运行历史" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "复核与保存" })).toBeVisible();
  });

  it("keeps an explicitly active review tab instead of remapping it to run", async () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("review");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(await screen.findByRole("heading", { name: "复核与保存" })).toBeVisible();
    expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("review");
    expect(screen.queryByText("任务进展")).not.toBeInTheDocument();
  });

  it("focuses review by default for completed runs with pending review", async () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    await waitFor(() =>
      expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("review"),
    );
    expect(screen.getByRole("heading", { name: "复核与保存" })).toBeVisible();
  });

  it("does not focus or count review for hidden-only committable outputs", async () => {
    useExecutionStore.getState().upsertExecution(makeHiddenOnlyCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-hidden");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    await waitFor(() =>
      expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("overview"),
    );
    expect(screen.queryByRole("button", { name: "复核" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "复核与保存" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /保存到工作区/ })).not.toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();

    act(() => {
      useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("review");
    });

    expect(await screen.findByText("暂无待复核内容")).toBeVisible();
    expect(screen.queryByText("隐藏背景记忆")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /保存到工作区/ })).not.toBeInTheDocument();
  });

  it("preserves an explicit tab choice after review becomes available", async () => {
    useExecutionStore.getState().upsertExecution(makeRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("evidence");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.getByRole("button", { name: "证据" })).toBeInTheDocument();

    act(() => {
      useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    });

    await waitFor(() =>
      expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("evidence"),
    );
    expect(screen.queryByRole("heading", { name: "复核与保存" })).not.toBeInTheDocument();
  });

  it("preserves manual overview focus after review becomes available", async () => {
    useExecutionStore.getState().upsertExecution(makeRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.getByText("任务进展")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "总览" }));

    act(() => {
      useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    });

    await waitFor(() =>
      expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("overview"),
    );
    expect(screen.queryByRole("heading", { name: "复核与保存" })).not.toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("manually saves default-selected completed outputs and exposes saved links", async () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "保存到工作区（2 项）" }));

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/executions/exec-1/commit",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ accepted_ids: ["doc-1", "lib-1"] }),
        }),
      ),
    );
    await waitFor(() =>
      expect(
        useExecutionStore.getState().executions.get("exec-1")?.result?.commit_state,
      ).toEqual(COMMITTED_STATE),
    );
    expect(
      await screen.findByRole("link", { name: "打开已保存的 Thesis outline" }),
    ).toBeInTheDocument();
  });

  it("accepts concrete ChangeSet units before saving mapped outputs", async () => {
    mockFetch.mockImplementation((url, init) => {
      if (String(url).endsWith("/api/executions/exec-1/changeset/accept")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(makeAcceptedChangeSetResponse(["unit-doc-1"])),
        });
      }
      if (String(url).endsWith("/api/executions/exec-1/commit")) {
        return Promise.resolve({
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
      }
      return Promise.reject(new Error(`Unexpected fetch: ${String(url)} ${init?.method ?? ""}`));
    });
    useExecutionStore.getState().upsertExecution(makeChangeSetCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    await screen.findByRole("heading", { name: "复核与保存" });
    expect(screen.queryByRole("button", { name: /保存到工作区/ })).not.toBeInTheDocument();
    expect(screen.getByText("文档 / 文档")).toBeInTheDocument();
    expect(screen.getByText("影响位置")).toBeInTheDocument();
    expect(screen.getByText("outline.md")).toBeInTheDocument();
    expect(screen.getByText("写入方式")).toBeInTheDocument();
    expect(screen.getByText("随已确认结果保存")).toBeInTheDocument();
    expect(screen.getByText("变更内容")).toBeInTheDocument();
    expect(screen.getAllByText("Update outline").length).toBeGreaterThan(0);
    expect(screen.queryByText("技术变更")).not.toBeInTheDocument();
    expect(screen.queryByText("documents / document")).not.toBeInTheDocument();
    expect(screen.queryByText("output_id")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("全选低/中风险"));
    expect(screen.getByLabelText("选择变更 Thesis outline")).toBeChecked();
    fireEvent.click(screen.getByText("确认选中"));

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/executions/exec-1/changeset/accept",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ unit_ids: ["unit-doc-1"] }),
        }),
      ),
    );
    await waitFor(() =>
      expect(
        (
          useExecutionStore.getState().executions.get("exec-1")?.result
            ?.change_set_review_state as { accepted_unit_ids?: string[] } | undefined
        )?.accepted_unit_ids,
      ).toEqual(["unit-doc-1"]),
    );
    expect(screen.getByRole("button", { name: "保存到工作区（1 项）" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "保存到工作区（1 项）" }));

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

  it("keeps the review tab visible after all ChangeSet units leave pending review", async () => {
    useExecutionStore.getState().upsertExecution(makeReviewedChangeSetCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(await screen.findByRole("button", { name: "复核" })).toBeInTheDocument();
    expect(screen.queryByText("1 项变更待复核。")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "复核" }));

    expect(screen.getByRole("heading", { name: "复核与保存" })).toBeVisible();
    expect(screen.getByText("0 项变更待复核。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存到工作区（1 项）" })).toBeInTheDocument();
  });

  it("renders automatically applied draft ChangeSet units as read-only review evidence", async () => {
    useExecutionStore
      .getState()
      .upsertExecution(makeDraftAppliedChangeSetCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("review");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    const checkbox = await screen.findByLabelText("Thesis outline 已阻断或不可批量选择");
    expect(checkbox).toBeDisabled();
    expect(screen.getByRole("button", { name: "确认 Thesis outline" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "拒绝 Thesis outline" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "撤销 Thesis outline" })).toBeDisabled();
    expect(
      screen.getByText(/已自动应用为草稿/),
    ).toBeInTheDocument();
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

  it("undoes a committed run from the run writeback status", async () => {
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

  it("shows an inline error when manual save response lacks backend commit_state", async () => {
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

    fireEvent.click(await screen.findByRole("button", { name: "保存到工作区（2 项）" }));

    expect(
      await screen.findByText("保存状态同步失败，请刷新后重试"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试保存（2 项）" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "打开已保存的 Thesis outline" })).not.toBeInTheDocument();
  });

  it("shows an inline error when manual save response commit_state is malformed", async () => {
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

    fireEvent.click(await screen.findByRole("button", { name: "保存到工作区（2 项）" }));

    expect(
      await screen.findByText("保存状态同步失败，请刷新后重试"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试保存（2 项）" })).toBeInTheDocument();
  });

  it("does not finalize the selected run when a prior manual save resolves after switching runs", async () => {
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

    fireEvent.click(await screen.findByRole("button", { name: "保存到工作区（2 项）" }));
    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ commit_state: COMMITTED_STATE_DOC2 }),
    });
    act(() => {
      useWorkbenchLayoutStore.getState().selectRun("exec-2");
    });
    expect(screen.getByText("1 项内容需要确认后再保存。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存到工作区（1 项）" }));
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
    expect(
      screen.queryByRole("link", { name: "打开已保存的 Thesis outline" }),
    ).not.toBeInTheDocument();
  });

  it("does not expose the product tab or memory snippets in the workbench chrome", () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.queryByRole("button", { name: "产物" })).not.toBeInTheDocument();
    expect(screen.getByText("2 项内容需要确认后再保存。")).toBeInTheDocument();
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

  it("renders found verified and used evidence summary from projected mission state", async () => {
    useExecutionStore.getState().upsertExecution(makeEvidenceMissionRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-evidence");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("evidence");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(await screen.findByText(/已发现\s*2 项/)).toBeInTheDocument();
    expect(screen.getByText(/已核验\s*1 项/)).toBeInTheDocument();
    expect(screen.getByText(/已采用\s*0 项/)).toBeInTheDocument();
    expect(screen.getByText("用于当前结论的证据采用情况。")).toBeInTheDocument();
  });

  it("preserves manual evidence focus when a run completes with review", async () => {
    useExecutionStore.getState().upsertExecution(makeRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("evidence");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(screen.queryByRole("button", { name: /自动聚焦/ })).not.toBeInTheDocument();

    act(() => {
      useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    });

    await waitFor(() =>
      expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("evidence"),
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
    expect(screen.getByText("起草内容")).toBeVisible();
    expect(screen.queryByText("输入预览")).not.toBeInTheDocument();
    expect(screen.queryByText("输出预览")).not.toBeInTheDocument();
    expect(screen.queryByText("联邦学习结合大模型")).not.toBeInTheDocument();
    for (const element of screen.getAllByText(/literature_synthesizer/)) {
      expect(element).not.toBeVisible();
    }
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

  it("keeps the idle overview in a chat-first empty state without capability launchers", () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({ sendMessage });

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    expect(
      screen.getAllByText("还没有正在执行的研究任务。直接在左侧描述你想推进的论文、实验或材料。").length,
    ).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "文献定位与创新点" })).not.toBeInTheDocument();
    expect(screen.queryByText("能力已就绪")).not.toBeInTheDocument();
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("does not send a launch prompt from overview interactions", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({ sendMessage });
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useExecutionStore.getState().upsertExecution(makeSecondCompletedRecord());

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "总览" }));
    fireEvent.click(await screen.findByRole("button", { name: "打开当前运行" }));

    await waitFor(() =>
      expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("run"),
    );
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("shows mission progress in overview for an active run", async () => {
    useExecutionStore.getState().upsertExecution(makeTeamRunningRecord());

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "总览" }));
    expect(await screen.findByText("当前任务")).toBeInTheDocument();
    expect(screen.getAllByText("团队调研").length).toBeGreaterThan(0);
    expect(screen.getByText("准备材料")).toBeInTheDocument();
  });

  it("keeps blocked and high-risk review items out of bulk accept", async () => {
    useExecutionStore.getState().upsertExecution(makeChangeSetCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("review");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "全选低/中风险待复核变更" }));

    expect(screen.getByLabelText("选择变更 Thesis outline")).toBeChecked();
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(checkboxes).toHaveLength(2);
    expect(checkboxes.filter((element) => element.checked)).toHaveLength(1);
    expect(screen.getByRole("button", { name: "确认选中变更" })).toBeEnabled();
  });

  it("sends intervention through chat orchestration with natural prompt metadata", async () => {
    const sendMessage = vi.fn().mockResolvedValue(undefined);
    useChatStoreV2.setState({ sendMessage });
    useExecutionStore.getState().upsertExecution(makeRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    fireEvent.click(screen.getByRole("button", { name: "中断并补充" }));
    fireEvent.change(
      screen.getByPlaceholderText(
        "补充新的约束、方向或纠错信息。问津会先在安全点中断当前任务，再通过对话继续编排后续处理。",
      ),
      { target: { value: "请优先补齐证据映射。" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "提交介入" }));

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/executions/exec-1/cancel?action=interrupt",
        expect.objectContaining({ method: "POST" }),
      ),
    );

    act(() => {
      useExecutionStore.getState().upsertExecution({
        ...makeRunningRecord(),
        status: "cancelled",
      });
    });

    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    const [, prompt, , options] = sendMessage.mock.calls[0];
    expect(prompt).toContain("请基于当前任务继续处理。");
    expect(prompt).toContain("上一轮执行 ID：exec-1");
    expect(prompt).toContain("补充说明：");
    expect(prompt).not.toContain("启动新 run");
    expect(options.metadata).toMatchObject({
      intervention: true,
      execution_id: "exec-1",
      interrupted_execution_id: "exec-1",
      orchestration: {
        intervention: true,
        execution_id: "exec-1",
        interrupted_execution_id: "exec-1",
      },
    });
    expect(options.metadata.orchestration).not.toHaveProperty("feature_id");
  });

  it("keeps review selected ahead of an unrelated active run", async () => {
    useExecutionStore.getState().upsertExecution(makeRunningRecord());
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useRunUiStore.getState().focusRun("exec-1");
    useRunUiStore.getState().markRunLaunching("run-1");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    await waitFor(() =>
      expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("review"),
    );
    expect(useWorkbenchLayoutStore.getState().selectedRunId).toBe("exec-1");
    expect(screen.getByRole("heading", { name: "复核与保存" })).toBeVisible();
  });

  it("opens the selected run from overview instead of the latest history row", async () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());
    useExecutionStore.getState().upsertExecution(makeSecondCompletedRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-1");

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "总览" }));
    fireEvent.click(await screen.findByRole("button", { name: "打开当前运行" }));

    await waitFor(() =>
      expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("run"),
    );
    expect(useWorkbenchLayoutStore.getState().selectedRunId).toBe("exec-1");
  });

  it("keeps review prioritized when pending review exists", async () => {
    useExecutionStore.getState().upsertExecution(makeCompletedRecord());

    render(<LiveWorkflowPanel workspaceId="ws-1" />);

    await waitFor(() =>
      expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("review"),
    );
    expect(screen.getByRole("heading", { name: "复核与保存" })).toBeVisible();
  });
});

function visibleOutsideClosedDetails(text: string) {
  return screen.queryAllByText(text).filter((element) => {
    const details = element.closest("details");
    return !details || details.open;
  });
}
