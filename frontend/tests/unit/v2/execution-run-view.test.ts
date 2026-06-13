import { describe, expect, it } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import { runViewFromExecution } from "@/lib/execution-run-view";

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
});
