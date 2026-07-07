import { describe, expect, it } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import type { RunRecord } from "@/lib/api/v2/runs";
import {
  buildRunProgressItems,
  mergeRunViews,
  runViewFromExecution,
  runViewFromResultCard,
  runViewFromRunRecord,
} from "@/lib/execution-run-view";
import {
  acceptedOutputIdsFromChangeSet,
  acceptedUnitIdsFromChangeSet,
  changeSetViewFromResult,
  commitPreviewsForChangeSetReview,
  responseResultPatch,
  type ExecutionChangeSetResponse,
} from "@/lib/change-set-view";
import { buildWorkspaceResultPreviewsFromOutputs } from "@/lib/workspace-result-preview";

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

  it("projects progress into student-facing task stages", () => {
    const record = baseRecord({
      graph_structure: {
        mode: "team_kernel",
        nodes: [
          { id: "team_prepare", type: "system", label: "team_prepare" },
          { id: "team_recruit", type: "system", label: "team_recruit" },
          { id: "team_dispatch", type: "system", label: "team_dispatch" },
          { id: "team_quality_gate", type: "system", label: "team_quality_gate" },
          { id: "team_finish", type: "system", label: "team_finish" },
        ],
        edges: [],
      },
      node_states: {
        "team.1.research_scout_v1.1": {
          status: "completed",
          node_type: "agent_invocation",
          label: "文献猎手 Nora",
          node_metadata: {
            team: true,
            template_id: "research_scout.v1",
            display_name: "文献猎手 Nora",
          },
        },
      },
    });

    const items = buildRunProgressItems(record);

    expect(items.map((item) => item.title)).toEqual([
      "准备材料",
      "组织研究小组",
      "查找证据并起草内容",
      "检查质量",
      "等待复核",
    ]);
    expect(items.map((item) => item.phaseTitle)).toEqual([
      "准备材料",
      "组织研究小组",
      "查找证据并起草内容",
      "检查质量",
      "等待复核",
    ]);
    expect(items.map((item) => item.title).join(" ")).not.toContain("team_");
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

  it("projects ChangeSet decisions and pending review counts", () => {
    const record = baseRecord({
      status: "completed",
      result: {
        change_set: {
          execution_id: "exec-1",
          workspace_id: "ws-1",
          write_mode: "ask_workspace_write",
          summary: "Two concrete workspace changes.",
          created_at: "2026-06-13T00:00:02Z",
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
              risk_reasons: ["document content changes require review"],
              default_apply_state: "staged",
              requires_confirmation: true,
              diff: { title: "Thesis outline", summary: "Update outline" },
              provenance: { output_id: "doc-1" },
              rollback: {},
            },
            {
              id: "unit-claim-1",
              target: {
                room: "documents",
                object_type: "claim",
                object_id: "claim-1",
              },
              action: "insert_claim",
              risk: "high",
              risk_reasons: ["unsupported claim"],
              default_apply_state: "blocked",
              requires_confirmation: true,
              diff: { title: "Unsupported claim" },
              provenance: { output_id: "doc-2" },
              rollback: {},
            },
          ],
        },
        change_set_review_state: {
          schema_version: "wenjin.change_set.review_state.v1",
          accepted_unit_ids: ["unit-doc-1"],
          rejected_unit_ids: [],
          undone_unit_ids: [],
          updated_at: "2026-06-13T00:00:03Z",
        },
      },
    });

    const view = runViewFromExecution(record);

    expect(view.changeSet?.counts.accepted).toBe(1);
    expect(view.changeSet?.counts.blocked).toBe(1);
    expect(view.pendingReviewCount).toBe(1);
    expect(view.changeSet?.units[0]).toMatchObject({
      id: "unit-doc-1",
      state: "accepted",
      group: "accepted",
      title: "Thesis outline",
      outputId: "doc-1",
    });
    expect(acceptedOutputIdsFromChangeSet(view.changeSet)).toEqual(["doc-1"]);
  });

  it("uses the latest live pending review count instead of stale historical maximum", () => {
    const changeSet = {
      execution_id: "exec-1",
      workspace_id: "ws-1",
      write_mode: "ask_workspace_write",
      summary: "Review document write.",
      created_at: "2026-06-13T00:00:02Z",
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
          risk_reasons: [],
          default_apply_state: "staged",
          requires_confirmation: true,
          diff: { title: "Thesis outline" },
          provenance: { output_id: "doc-1" },
          rollback: {},
        },
      ],
    };
    const historical = runViewFromExecution(
      baseRecord({
        status: "completed",
        result: {
          change_set: changeSet,
          change_set_review_state: {
            accepted_unit_ids: [],
            rejected_unit_ids: [],
            undone_unit_ids: [],
          },
        },
      }),
    );
    const live = runViewFromExecution(
      baseRecord({
        status: "completed",
        result: {
          change_set: changeSet,
          change_set_review_state: {
            accepted_unit_ids: ["unit-doc-1"],
            rejected_unit_ids: [],
            undone_unit_ids: [],
          },
        },
      }),
    );

    expect(historical.pendingReviewCount).toBe(1);
    expect(live.pendingReviewCount).toBe(0);
    expect(mergeRunViews(live, historical).pendingReviewCount).toBe(0);
  });

  it("does not bridge blocked ChangeSet units into historical output commits", () => {
    const changeSet = changeSetViewFromResult({
      change_set: {
        execution_id: "exec-1",
        workspace_id: "ws-1",
        write_mode: "strict_review",
        summary: "Blocked and accepted units.",
        created_at: "2026-06-13T00:00:02Z",
        units: [
          {
            id: "unit-doc-1",
            target: { room: "documents", object_type: "document", object_id: "doc-1" },
            action: "write_document_draft",
            risk: "medium",
            risk_reasons: [],
            default_apply_state: "staged",
            requires_confirmation: true,
            diff: { title: "Draft" },
            provenance: { output_id: "doc-1" },
            rollback: {},
          },
          {
            id: "unit-claim-1",
            target: { room: "documents", object_type: "claim", object_id: "claim-1" },
            action: "insert_claim",
            risk: "high",
            risk_reasons: ["unsupported claim"],
            default_apply_state: "blocked",
            requires_confirmation: true,
            diff: { title: "Claim" },
            provenance: { output_id: "doc-2" },
            rollback: {},
          },
        ],
      },
      change_set_review_state: {
        accepted_unit_ids: ["unit-doc-1", "unit-claim-1"],
        rejected_unit_ids: [],
        undone_unit_ids: [],
      },
    });

    expect(acceptedOutputIdsFromChangeSet(changeSet)).toEqual(["doc-1"]);
  });

  it("requires every ChangeSet unit for the same output to be accepted before commit bridging", () => {
    const changeSet = changeSetViewFromResult({
      change_set: {
        execution_id: "exec-1",
        workspace_id: "ws-1",
        write_mode: "ask_workspace_write",
        summary: "Composite document write.",
        created_at: "2026-06-13T00:00:02Z",
        units: [
          {
            id: "unit-outline",
            target: { room: "documents", object_type: "document", object_id: "doc-1" },
            action: "write_document_draft",
            risk: "medium",
            risk_reasons: [],
            default_apply_state: "staged",
            requires_confirmation: true,
            diff: { title: "Outline" },
            provenance: { output_id: "doc-1" },
            rollback: {},
          },
          {
            id: "unit-claim",
            target: { room: "documents", object_type: "claim", object_id: "claim-1" },
            action: "insert_claim",
            risk: "medium",
            risk_reasons: [],
            default_apply_state: "staged",
            requires_confirmation: true,
            diff: { title: "Claim" },
            provenance: { output_id: "doc-1" },
            rollback: {},
          },
        ],
      },
      change_set_review_state: {
        accepted_unit_ids: ["unit-outline"],
        rejected_unit_ids: [],
        undone_unit_ids: [],
      },
    });

    expect(acceptedOutputIdsFromChangeSet(changeSet)).toEqual([]);
  });

  it("bridges an output only when all related ChangeSet units are accepted and unblocked", () => {
    const changeSet = changeSetViewFromResult({
      change_set: {
        execution_id: "exec-1",
        workspace_id: "ws-1",
        write_mode: "ask_workspace_write",
        summary: "Composite document write.",
        created_at: "2026-06-13T00:00:02Z",
        units: [
          {
            id: "unit-outline",
            target: { room: "documents", object_type: "document", object_id: "doc-1" },
            action: "write_document_draft",
            risk: "medium",
            risk_reasons: [],
            default_apply_state: "staged",
            requires_confirmation: true,
            diff: { title: "Outline" },
            provenance: { output_id: "doc-1" },
            rollback: {},
          },
          {
            id: "unit-claim",
            target: { room: "documents", object_type: "claim", object_id: "claim-1" },
            action: "insert_claim",
            risk: "medium",
            risk_reasons: [],
            default_apply_state: "staged",
            requires_confirmation: true,
            diff: { title: "Claim" },
            provenance: { output_id: "doc-1" },
            rollback: {},
          },
        ],
      },
      change_set_review_state: {
        accepted_unit_ids: ["unit-outline", "unit-claim"],
        rejected_unit_ids: [],
        undone_unit_ids: [],
      },
    });

    expect(acceptedOutputIdsFromChangeSet(changeSet)).toEqual(["doc-1"]);
  });

  it("includes accepted materialized units without historical output ids", () => {
    const changeSet = changeSetViewFromResult({
      change_set: {
        execution_id: "exec-1",
        workspace_id: "ws-1",
        write_mode: "ask_workspace_write",
        summary: "Settings and sandbox writes.",
        created_at: "2026-06-13T00:00:02Z",
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
            risk_reasons: [],
            default_apply_state: "staged",
            requires_confirmation: true,
            diff: { title: "写入前询问" },
            provenance: { source_review_item_id: "settings-1" },
            rollback: {},
            materialization: {
              operation: "settings.update",
              payload: { write_mode: "ask_workspace_write" },
            },
          },
          {
            id: "unit-sandbox-1",
            target: {
              room: "sandbox",
              object_type: "sandbox_artifact",
              object_id: "artifact-1",
            },
            action: "accept_sandbox_artifact",
            risk: "low",
            risk_reasons: [],
            default_apply_state: "staged",
            requires_confirmation: true,
            diff: { title: "实验报告" },
            provenance: { source_review_item_id: "artifact-1" },
            rollback: {},
            materialization: {
              operation: "sandbox.materialize_artifact",
              payload: {
                artifact_id: "artifact-1",
                review_item_id: "artifact-review-1",
              },
            },
          },
          {
            id: "unit-review-note-1",
            target: {
              room: "review",
              object_type: "review_note",
              object_id: "note-1",
            },
            action: "acknowledge_review_note",
            risk: "low",
            risk_reasons: [],
            default_apply_state: "staged",
            requires_confirmation: true,
            diff: { title: "仅复核备注" },
            provenance: { source_review_item_id: "note-1" },
            rollback: {},
          },
          {
            id: "unit-blocked-1",
            target: { room: "settings", object_type: "workspace_settings" },
            action: "update_workspace_settings",
            risk: "high",
            risk_reasons: ["requires admin review"],
            default_apply_state: "blocked",
            requires_confirmation: true,
            diff: { title: "高风险设置" },
            provenance: { source_review_item_id: "settings-2" },
            rollback: {},
            materialization: {
              operation: "settings.update",
              payload: { write_mode: "strict_review" },
            },
          },
        ],
      },
      change_set_review_state: {
        accepted_unit_ids: [
          "unit-settings-1",
          "unit-sandbox-1",
          "unit-review-note-1",
          "unit-blocked-1",
        ],
        rejected_unit_ids: [],
        undone_unit_ids: [],
      },
    });

    expect(acceptedOutputIdsFromChangeSet(changeSet)).toEqual([]);
    expect(acceptedUnitIdsFromChangeSet(changeSet)).toEqual([
      "unit-settings-1",
      "unit-sandbox-1",
    ]);
  });

  it("does not bridge an output when any related ChangeSet unit is blocked by default", () => {
    const changeSet = changeSetViewFromResult({
      change_set: {
        execution_id: "exec-1",
        workspace_id: "ws-1",
        write_mode: "strict_review",
        summary: "Blocked composite document write.",
        created_at: "2026-06-13T00:00:02Z",
        units: [
          {
            id: "unit-outline",
            target: { room: "documents", object_type: "document", object_id: "doc-1" },
            action: "write_document_draft",
            risk: "medium",
            risk_reasons: [],
            default_apply_state: "staged",
            requires_confirmation: true,
            diff: { title: "Outline" },
            provenance: { output_id: "doc-1" },
            rollback: {},
          },
          {
            id: "unit-claim",
            target: { room: "documents", object_type: "claim", object_id: "claim-1" },
            action: "insert_claim",
            risk: "high",
            risk_reasons: ["unsupported claim"],
            default_apply_state: "blocked",
            requires_confirmation: true,
            diff: { title: "Claim" },
            provenance: { output_id: "doc-1" },
            rollback: {},
          },
        ],
      },
      change_set_review_state: {
        accepted_unit_ids: ["unit-outline", "unit-claim"],
        rejected_unit_ids: [],
        undone_unit_ids: [],
      },
    });

    expect(acceptedOutputIdsFromChangeSet(changeSet)).toEqual([]);
  });

  it("uses visible default-checked previews as historical output commit candidates", () => {
    const previews = buildWorkspaceResultPreviewsFromOutputs([
      {
        id: "doc-1",
        kind: "document",
        preview: "Visible document",
        default_checked: true,
      },
      {
        id: "library-1",
        kind: "library_item",
        preview: "Visible library item",
        default_checked: false,
      },
      {
        id: "memory-1",
        kind: "memory_fact",
        preview: "Hidden memory update",
        default_checked: true,
      },
    ]);

    expect(
      commitPreviewsForChangeSetReview({ changeSet: null, previews }).map(
        (preview) => preview.id,
      ),
    ).toEqual(["doc-1"]);
  });

  it("uses accepted ChangeSet output ids as explicit commit candidates", () => {
    const previews = buildWorkspaceResultPreviewsFromOutputs([
      {
        id: "doc-1",
        kind: "document",
        preview: "Visible document",
        default_checked: false,
      },
      {
        id: "memory-1",
        kind: "memory_fact",
        preview: "Hidden memory update",
        default_checked: true,
      },
    ]);
    const changeSet = changeSetViewFromResult({
      change_set: {
        execution_id: "exec-1",
        workspace_id: "ws-1",
        write_mode: "ask_workspace_write",
        summary: "Accepted explicit memory write.",
        created_at: "2026-06-13T00:00:02Z",
        units: [
          {
            id: "unit-doc-1",
            target: { room: "documents", object_type: "document", object_id: "doc-1" },
            action: "write_document_draft",
            risk: "medium",
            risk_reasons: [],
            default_apply_state: "staged",
            requires_confirmation: true,
            diff: { title: "Document" },
            provenance: { output_id: "doc-1" },
            rollback: {},
          },
          {
            id: "unit-memory-1",
            target: { room: "memory", object_type: "fact", object_id: "memory-1" },
            action: "upsert_memory_fact",
            risk: "low",
            risk_reasons: [],
            default_apply_state: "staged",
            requires_confirmation: true,
            diff: { title: "Memory" },
            provenance: { output_id: "memory-1" },
            rollback: {},
          },
        ],
      },
      change_set_review_state: {
        accepted_unit_ids: ["unit-memory-1"],
        rejected_unit_ids: [],
        undone_unit_ids: [],
      },
    });

    expect(
      commitPreviewsForChangeSetReview({ changeSet, previews }).map(
        (preview) => preview.id,
      ),
    ).toEqual(["memory-1"]);
  });

  it("patches response unit states so stale result unit_states cannot mask review updates", () => {
    const changeSet: ExecutionChangeSetResponse["change_set"] = {
      execution_id: "exec-1",
      workspace_id: "ws-1",
      write_mode: "ask_workspace_write",
      summary: "Review document write.",
      created_at: "2026-06-13T00:00:02Z",
      units: [
        {
          id: "unit-doc-1",
          target: { room: "documents", object_type: "document", object_id: "doc-1" },
          action: "write_document_draft",
          risk: "medium",
          risk_reasons: [],
          default_apply_state: "staged",
          requires_confirmation: true,
          diff: { title: "Document" },
          provenance: { output_id: "doc-1" },
          rollback: {},
        },
      ],
    };
    const initialResult = {
      change_set: changeSet,
      change_set_review_state: {
        accepted_unit_ids: [],
        rejected_unit_ids: [],
        undone_unit_ids: [],
      },
      unit_states: [
        {
          unit_id: "unit-doc-1",
          default_apply_state: "staged",
          state: "staged",
        },
      ],
    };
    const response: ExecutionChangeSetResponse = {
      change_set: changeSet,
      review_state: {
        accepted_unit_ids: ["unit-doc-1"],
        rejected_unit_ids: [],
        undone_unit_ids: [],
        updated_at: "2026-06-13T00:00:04Z",
        schema_version: "wenjin.change_set.review_state.v1",
      },
      unit_states: [
        {
          unit_id: "unit-doc-1",
          default_apply_state: "staged",
          state: "accepted",
        },
      ],
    };

    const patchedView = changeSetViewFromResult({
      ...initialResult,
      ...responseResultPatch(response),
    });

    expect(patchedView?.units[0]?.state).toBe("accepted");
    expect(patchedView?.pendingCount).toBe(0);
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
    expect(view.summary).toBe("已保存到 1 个工作区房间。");
  });

  it("summarizes completed runs that still need confirmation", () => {
    const view = runViewFromExecution(
      baseRecord({
        status: "completed",
        result: {
          change_set: {
            execution_id: "exec-1",
            workspace_id: "ws-1",
            write_mode: "ask_workspace_write",
            summary: "Reviewable output changes.",
            created_at: "2026-06-20T00:00:00Z",
            units: [
              {
                id: "unit-doc-1",
                target: {
                  room: "documents",
                  object_type: "document",
                  object_id: "doc-1",
                },
                action: "write_document_draft",
                risk: "medium",
                risk_reasons: [],
                default_apply_state: "staged",
                requires_confirmation: true,
                diff: { title: "Document" },
                provenance: { output_id: "doc-1" },
                rollback: {},
              },
            ],
          },
          change_set_review_state: {
            accepted_unit_ids: [],
            rejected_unit_ids: [],
            undone_unit_ids: [],
          },
          task_report: {
            narrative: "已生成。",
            outputs: [],
          },
        },
      }),
    );

    expect(view.pendingReviewCount).toBe(1);
    expect(view.summary).toBe("1 项内容需要确认后再保存。");
  });

  it("projects compacted ChangeSet receipt after full review details are pruned", () => {
    const view = runViewFromExecution(
      baseRecord({
        status: "completed",
        result: {
          commit_state: COMMITTED_STATE,
          change_set_receipt: {
            schema_version: "wenjin.change_set.receipt.v1",
            retention: "compacted_after_commit",
            summary: "Reviewable output changes.",
            unit_count: 1,
            accepted_unit_ids: ["output-doc-1"],
            rejected_unit_ids: [],
            undone_unit_ids: [],
            accepted_output_ids: ["doc-1"],
            rejected_output_ids: [],
            committed_at: "2026-06-20T00:00:00Z",
            targets: {
              prism: [
                {
                  output_id: "doc-1",
                  item_id: "saved-doc-1",
                  path: "outline.md",
                  content_hash: "hash-after",
                },
              ],
              library: [],
              memory: [],
              decisions: [],
              tasks: [],
            },
          },
          task_report: {
            narrative: "已保存。",
            outputs: [],
          },
        },
      }),
    );

    expect(view.changeSet).toBeNull();
    expect(view.changeSetReceipt).toMatchObject({
      retention: "compacted_after_commit",
      summary: "Reviewable output changes.",
      unitCount: 1,
      acceptedOutputIds: ["doc-1"],
      committedAt: "2026-06-20T00:00:00Z",
    });
    expect(view.changeSetReceipt?.targets.prism[0]).toMatchObject({
      output_id: "doc-1",
      item_id: "saved-doc-1",
      path: "outline.md",
    });
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
            counts: { ...COMMITTED_STATE.counts, prism: 1.5 },
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
              prism: "bad",
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
              prism: COMMITTED_STATE.room_targets.prism,
            },
          },
        },
      }),
    );

    expect(sparseCountsView.commitState).toBeNull();
    expect(missingRoomTargetArraysView.commitState).toBeNull();
  });
});
