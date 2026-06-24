import { describe, expect, it } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import type { RunRecord } from "@/lib/api/v2/runs";
import {
  buildRunProgressItems,
  runViewFromExecution,
  runViewFromResultCard,
  runViewFromRunRecord,
} from "@/lib/execution-run-view";

const COMMITTED_STATE = {
  status: "committed",
  accepted_ids: ["doc-1"],
  rejected_ids: [],
  counts: { library: 0, documents: 1, memory: 0, decisions: 0, tasks: 0 },
  room_targets: {
    documents: [{ output_id: "doc-1", item_id: "saved-doc-1" }],
    library: [],
    memory: [],
    decisions: [],
    tasks: [],
  },
  committed_at: "2026-06-20T00:00:00Z",
} as const;

function baseRecord(overrides: Partial<ExecutionRecord>): ExecutionRecord {
  return {
    id: "exec-1",
    user_id: "user-1",
    workspace_id: "ws-1",
    execution_type: "capability",
    feature_id: "team_research",
    status: "running",
    params: {},
    node_states: {},
    artifact_ids: [],
    next_actions: [],
    child_execution_ids: [],
    progress: 50,
    created_at: "2026-06-13T00:00:00Z",
    updated_at: "2026-06-13T00:00:01Z",
    result: null,
    graph_structure: { mode: "team_kernel", nodes: [], edges: [] },
    ...overrides,
  };
}

describe("execution run view expert projection", () => {
  it("projects expert snapshots and preview items from node metadata", () => {
    const record = baseRecord({
      node_states: {
        "team.1.research_scout_v1.1": {
          status: "completed",
          node_type: "agent_invocation",
          label: "文献猎手 Nora",
          node_metadata: {
            team: true,
            template_id: "research_scout.v1",
            display_name: "文献猎手 Nora",
            assigned_role: "文献检索专家",
            expert_profile: {
              public_name: "文献猎手 Nora",
              role_title: "文献检索专家",
              avatar_label: "文",
              tone: "witty_professional",
            },
            harness: {
              expert_snapshots: [
                {
                  snapshot_id: "snap-1",
                  status: "running",
                  update_kind: "progress",
                  stage: { label: "检索中" },
                  headline: "扫文献雷达中",
                  body: "正在筛选候选来源。",
                  created_at: "2026-06-13T00:00:00Z",
                },
                {
                  snapshot_id: "snap-2",
                  status: "completed",
                  update_kind: "finding",
                  stage: { label: "检索完成" },
                  headline: "找到 12 篇候选文献",
                  body: "主要集中在隐私保护、通信压缩和个性化微调三个方向。",
                  chips: [{ label: "候选", value: "12 篇", tone: "success" }],
                  output_refs: [{ label: "候选列表", kind: "literature_list", preview_item_id: "preview-1" }],
                  created_at: "2026-06-13T00:00:01Z",
                },
              ],
              expert_preview_items: [
                {
                  preview_item_id: "preview-1",
                  owner_agent_invocation_id: "team.1.research_scout_v1.1",
                  title: "候选文献列表",
                  kind: "literature_list",
                  summary: "12 篇候选文献和筛选理由。",
                  status: "ready",
                  created_at: "2026-06-13T00:00:01Z",
                },
              ],
            },
          },
        },
      },
    });

    const view = runViewFromExecution(record);
    const member = view.team?.members[0];

    expect(member?.expertProfile?.publicName).toBe("文献猎手 Nora");
    expect(member?.expertProfile?.roleTitle).toBe("文献检索专家");
    expect(member?.latestSnapshot?.headline).toBe("找到 12 篇候选文献");
    expect(member?.snapshots).toHaveLength(2);
    expect(member?.previewItems[0]).toMatchObject({
      id: "preview-1",
      title: "候选文献列表",
      kind: "literature_list",
      status: "ready",
    });
  });

  it("does not treat non-team agent_invocation nodes as team members", () => {
    const record = baseRecord({
      node_states: {
        "technical-agent-node": {
          status: "running",
          node_type: "agent_invocation",
          label: "内部执行节点",
          node_metadata: {
            template_id: "internal_executor.v1",
            display_name: "内部执行节点",
          },
        },
        "team.1.research_scout_v1.1": {
          status: "running",
          node_type: "agent_invocation",
          label: "文献猎手 Nora",
          node_metadata: {
            team: true,
            template_id: "research_scout.v1",
            display_name: "文献猎手 Nora",
            assigned_role: "文献检索专家",
          },
        },
      },
    });

    const view = runViewFromExecution(record);

    expect(view.team?.members.map((member) => member.id)).toEqual([
      "team.1.research_scout_v1.1",
    ]);
  });

  it("sanitizes raw runtime text from progress item details", () => {
    const record = baseRecord({
      graph_structure: {
        nodes: [
          { id: "error-node", type: "agent_invocation", label: "Error node" },
          { id: "thinking-node", type: "agent_invocation", label: "Thinking node" },
          { id: "preview-node", type: "agent_invocation", label: "Preview node" },
        ],
        edges: [],
      },
      node_states: {
        "error-node": {
          status: "failed",
          error:
            '{"stderr":"raw stderr should stay hidden","ref":"/workspace/outputs/harness/exec-1/error.txt"}',
        },
        "thinking-node": {
          status: "running",
          thinking: "stdout: raw stdout should stay hidden",
        },
        "preview-node": {
          status: "completed",
          output_preview: "/workspace/outputs/harness/exec-1/preview.json",
        },
      },
    });

    const details = buildRunProgressItems(record).map((item) => item.detail).join("\n");

    expect(details).not.toContain("stdout");
    expect(details).not.toContain("stderr");
    expect(details).not.toContain("raw stdout should stay hidden");
    expect(details).not.toContain("raw stderr should stay hidden");
    expect(details).not.toContain("/workspace/outputs/harness");
    expect(details).not.toContain("{");
  });

  it("sanitizes raw ExecutionRecord summaries and failure messages", () => {
    const record = baseRecord({
      status: "failed",
      result_summary:
        '{"stdout":"raw summary should stay hidden","ref":"/workspace/outputs/harness/exec-1/result.json"}',
      last_error:
        '{"stderr":"raw error should stay hidden","ref":"/workspace/outputs/harness/exec-1/error.txt"}',
      result: {
        task_report: {
          narrative: "已生成论文结构建议。",
          errors: [
            {
              error:
                '{"stderr":"raw task error should stay hidden","ref":"/workspace/outputs/harness/exec-1/task-error.txt"}',
            },
          ],
        },
      },
    });

    const view = runViewFromExecution(record);
    const text = [view.summary, view.failureMessage].filter(Boolean).join("\n");

    expect(view.summary).toBe("已生成论文结构建议。");
    expect(view.failureMessage).toBe("运行问题已记录");
    expect(text).not.toContain("stdout");
    expect(text).not.toContain("stderr");
    expect(text).not.toContain("raw summary should stay hidden");
    expect(text).not.toContain("raw error should stay hidden");
    expect(text).not.toContain("/workspace/outputs/harness");
    expect(text).not.toContain("{");
  });

  it("sanitizes raw RunRecord summaries and failure messages", () => {
    const record: RunRecord = {
      id: "run-raw-1",
      workspace_id: "ws-1",
      capability_name: "实验实证结果包",
      status: "failed",
      started_at: "2026-06-13T00:00:00Z",
      summary:
        'stdout: raw run summary should stay hidden /workspace/outputs/harness/exec-1/summary.txt',
      failure_message:
        '{"stderr":"raw run error should stay hidden","ref":"/workspace/outputs/harness/exec-1/error.txt"}',
    };

    const view = runViewFromRunRecord(record, "ws-1");
    const text = [view.summary, view.failureMessage].filter(Boolean).join("\n");

    expect(view.summary).toBe("执行失败。");
    expect(view.failureMessage).toBe("运行问题已记录");
    expect(text).not.toContain("stdout");
    expect(text).not.toContain("stderr");
    expect(text).not.toContain("raw run summary should stay hidden");
    expect(text).not.toContain("raw run error should stay hidden");
    expect(text).not.toContain("/workspace/outputs/harness");
    expect(text).not.toContain("{");
  });

  it("sanitizes raw ResultCardData narratives and errors", () => {
    const view = runViewFromResultCard(
      {
        execution_id: "result-card-raw-1",
        capability_name: "图表生成",
        status: "failed",
        outputs: [],
        narrative:
          '{"stdout":"raw result-card narrative should stay hidden","ref":"/workspace/outputs/harness/exec-1/result.json"}',
        errors: [
          {
            message:
              'stderr: raw result-card error should stay hidden /workspace/outputs/harness/exec-1/error.txt',
          },
        ],
      },
      "ws-1",
    );
    const text = [view.summary, view.failureMessage].filter(Boolean).join("\n");

    expect(view.summary).toBe("执行失败。");
    expect(view.failureMessage).toBe("运行问题已记录");
    expect(text).not.toContain("stdout");
    expect(text).not.toContain("stderr");
    expect(text).not.toContain("raw result-card narrative should stay hidden");
    expect(text).not.toContain("raw result-card error should stay hidden");
    expect(text).not.toContain("/workspace/outputs/harness");
    expect(text).not.toContain("{");
  });

  it("projects durable commitState from ExecutionRecord results", () => {
    const view = runViewFromExecution(
      baseRecord({
        status: "completed",
        result: {
          commit_state: COMMITTED_STATE,
          task_report: {
            narrative: "已保存。",
            outputs: [],
          },
        },
      }),
    );

    expect(view.commitState).toEqual(COMMITTED_STATE);
  });

  it("projects durable commitState from ResultCardData", () => {
    const view = runViewFromResultCard(
      {
        execution_id: "result-card-commit-1",
        capability_name: "资料整理",
        status: "completed",
        outputs: [],
        narrative: "已生成。",
        commit_state: COMMITTED_STATE,
      } as Parameters<typeof runViewFromResultCard>[0] & {
        commit_state: typeof COMMITTED_STATE;
      },
      "ws-1",
    );

    expect(view.commitState).toEqual(COMMITTED_STATE);
  });

  it("drops malformed commitState missing required counts or room targets", () => {
    const missingCountsView = runViewFromExecution(
      baseRecord({
        status: "completed",
        result: {
          commit_state: {
            status: COMMITTED_STATE.status,
            accepted_ids: COMMITTED_STATE.accepted_ids,
            rejected_ids: COMMITTED_STATE.rejected_ids,
            room_targets: COMMITTED_STATE.room_targets,
            committed_at: COMMITTED_STATE.committed_at,
          },
        },
      }),
    );
    const missingRoomTargetsView = runViewFromExecution(
      baseRecord({
        status: "completed",
        result: {
          commit_state: {
            status: COMMITTED_STATE.status,
            accepted_ids: COMMITTED_STATE.accepted_ids,
            rejected_ids: COMMITTED_STATE.rejected_ids,
            counts: COMMITTED_STATE.counts,
            committed_at: COMMITTED_STATE.committed_at,
          },
        },
      }),
    );

    expect(missingCountsView.commitState).toBeNull();
    expect(missingRoomTargetsView.commitState).toBeNull();
  });

  it("drops malformed commitState with non-integer counts or bad room target values", () => {
    const nonIntegerCountView = runViewFromExecution(
      baseRecord({
        status: "completed",
        result: {
          commit_state: {
            ...COMMITTED_STATE,
            counts: { ...COMMITTED_STATE.counts, documents: 1.5 },
          },
        },
      }),
    );
    const malformedRoomTargetView = runViewFromExecution(
      baseRecord({
        status: "completed",
        result: {
          commit_state: {
            ...COMMITTED_STATE,
            room_targets: {
              ...COMMITTED_STATE.room_targets,
              documents: "bad",
            },
          },
        },
      }),
    );
    const unknownRoomTargetView = runViewFromExecution(
      baseRecord({
        status: "completed",
        result: {
          commit_state: {
            ...COMMITTED_STATE,
            room_targets: {
              ...COMMITTED_STATE.room_targets,
              archive: [],
            },
          },
        },
      }),
    );

    expect(nonIntegerCountView.commitState).toBeNull();
    expect(malformedRoomTargetView.commitState).toBeNull();
    expect(unknownRoomTargetView.commitState).toBeNull();
  });

  it("drops sparse commitState missing required count keys or room target arrays", () => {
    const sparseCountsView = runViewFromExecution(
      baseRecord({
        status: "completed",
        result: {
          commit_state: {
            ...COMMITTED_STATE,
            counts: {},
          },
        },
      }),
    );
    const missingRoomTargetArraysView = runViewFromExecution(
      baseRecord({
        status: "completed",
        result: {
          commit_state: {
            ...COMMITTED_STATE,
            room_targets: {
              documents: COMMITTED_STATE.room_targets.documents,
            },
          },
        },
      }),
    );

    expect(sparseCountsView.commitState).toBeNull();
    expect(missingRoomTargetArraysView.commitState).toBeNull();
  });
});
