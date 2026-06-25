import { describe, expect, it } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import {
  buildRunProgressItems,
  mergeRunViews,
  runViewFromExecution,
  runViewFromResultCard,
  runViewFromRunRecord,
} from "@/lib/execution-run-view";

function makeExecution(
  overrides: Partial<ExecutionRecord> = {},
): ExecutionRecord {
  return {
    id: "exec-1",
    user_id: "user-1",
    workspace_id: "ws-1",
    execution_type: "feature",
    feature_id: "sci_literature_positioning",
    display_name: "文献定位与创新点",
    status: "running",
    params: {},
    node_states: {},
    artifact_ids: [],
    next_actions: [],
    child_execution_ids: [],
    progress: 25,
    created_at: "2026-05-22T00:00:00Z",
    started_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:10Z",
    ...overrides,
  };
}

describe("execution run view projection", () => {
  it("projects a live execution into a focused run view", () => {
    const view = runViewFromExecution(
      makeExecution({
        graph_structure: {
          nodes: [
            { id: "n1", type: "react" },
            { id: "n2", type: "react" },
          ],
          edges: [],
        },
        node_states: {
          n1: { status: "completed", token_usage: { input: 3, output: 5 } },
          n2: { status: "running" },
        },
      }),
    );

    expect(view.id).toBe("exec-1");
    expect(view.title).toBe("文献定位与创新点");
    expect(view.status).toBe("running");
    expect(view.nodeCount).toBe(2);
    expect(view.completedNodeCount).toBe(1);
    expect(view.tokenUsage).toEqual({ input: 3, output: 5 });
    expect(view.actions).toContain("open_live");
  });

  it("humanizes technical capability ids when a run has no display name", () => {
    const view = runViewFromExecution(
      makeExecution({
        display_name: null,
        feature_id: "sci_literature_positioning",
      }),
    );

    expect(view.title).toBe("文献定位与创新点");
    expect(view.title).not.toContain("sci_literature_positioning");
  });

  it("detects Prism changes from completed execution review items", () => {
    const view = runViewFromExecution(
      makeExecution({
        status: "completed",
        completed_at: "2026-05-22T00:00:30Z",
        result_summary: "完成 文献定位与创新点",
        review_items: [
          {
            id: "review-1",
            kind: "prism_file_change",
            logical_key: "section:intro",
            status: "pending",
            title: "Intro",
          },
        ],
      }),
    );

    expect(view.status).toBe("completed");
    expect(view.hasPrismChanges).toBe(true);
    expect(view.prismReviewCount).toBe(1);
    expect(view.actions).toContain("open_prism");
  });

  it("detects sandbox artifacts from completed execution review items", () => {
    const view = runViewFromExecution(
      makeExecution({
        status: "completed",
        review_items: [
          {
            id: "review-1",
            kind: "sandbox_artifact",
            status: "pending",
            title: "Sandbox result",
            target: {
              kind: "sandbox_artifact",
              path: "/workspace/outputs/result.json",
              artifact_kind: "sandbox_output",
            },
          },
        ],
      }),
    );

    expect(view.primarySurface).toBe("sandbox");
    expect(view.hasPrismChanges).toBe(false);
    expect(view.hasSandboxArtifacts).toBe(true);
    expect(view.sandboxReviewCount).toBe(1);
    expect(view.actions).toContain("preview_results");
  });

  it("projects academic review packets into run summaries and quality highlights", () => {
    const view = runViewFromExecution(
      makeExecution({
        status: "failed_partial",
        result: {
          task_report: {
            capability_id: "sci_literature_positioning",
            status: "failed_partial",
            review_packet: {
              packet_id: "packet-1",
              title: "文献定位候选结果",
              summary: "1 项可保存，1 项需要确认。",
              completion_status: "partial",
              items: [
                {
                  item_id: "artifact-1",
                  kind: "artifact",
                  title: "检索证据包",
                  summary: "保留了来源筛选记录。",
                  artifact_refs: ["artifact:/workspace/outputs/sources.json"],
                  risk: { level: "low", reasons: [] },
                },
                {
                  item_id: "warning-1",
                  kind: "warning",
                  title: "弱证据或未支持论断",
                  summary: "AAAI 适配性还缺少直接证据。",
                  risk: { level: "high", reasons: ["unsupported"] },
                  can_commit: false,
                },
              ],
            },
          },
        },
      }),
    );

    expect(view.reviewPacket?.items).toHaveLength(2);
    expect(view.reviewPacket?.supportedCount).toBe(1);
    expect(view.reviewPacket?.needsConfirmationCount).toBe(0);
    expect(view.reviewPacket?.blockerCount).toBe(1);
    expect(view.reviewPacket?.items[1]?.supportState).toBe("blocker");
    expect(view.sandboxReviewCount).toBe(1);
    expect(view.actions).toContain("preview_results");
    expect(view.qualityHighlights).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "结果完整性", status: "warning" }),
        expect.objectContaining({ label: "证据风险", status: "fail" }),
      ]),
    );
  });

  it("classifies partial node failures", () => {
    const view = runViewFromExecution(
      makeExecution({
        status: "failed_partial",
        node_states: {
          scout: { status: "failed" },
        },
        result: {
          task_report: {
            capability_id: "sci_literature_positioning",
            status: "failed_partial",
            errors: [{ error: "search source failed" }],
          },
        },
      }),
    );

    expect(view.failureCategory).toBe("node_failed");
    expect(view.failureMessage).toBe("search source failed");
    expect(view.actions).toContain("preview_results");
  });

  it("projects dynamic team members from agent invocation node metadata", () => {
    const view = runViewFromExecution(
      makeExecution({
        graph_structure: {
          mode: "team_kernel",
          nodes: [],
          edges: [],
        } as ExecutionRecord["graph_structure"],
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
        } as ExecutionRecord["node_states"],
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
      }),
    );

    expect(view.team).toEqual({
      mode: "team_kernel",
      members: [
        {
          id: "research_scholar.v1__1",
          templateId: "research_scholar.v1",
          displayName: "文献专家",
          status: "completed",
          effectiveTools: ["web_search", "library_read"],
          effectiveSkills: ["literature_search.v1"],
          snapshots: [],
          previewItems: [],
        },
        {
          id: "critical_reviewer.v1__1",
          templateId: "critical_reviewer.v1",
          displayName: "质量审稿人",
          status: "running",
          effectiveTools: ["library_read"],
          effectiveSkills: ["critical_review.v1"],
          snapshots: [],
          previewItems: [],
        },
      ],
      qualityGates: [
        {
          id: "evidence_traceability",
          status: "warning",
          severity: "medium",
          nextAction: "revise_evidence_map",
        },
      ],
    });
  });

  it("deduplicates repeated quality gate events into the current team view", () => {
    const view = runViewFromExecution(
      makeExecution({
        graph_structure: {
          mode: "team_kernel",
          nodes: [],
          edges: [],
        } as ExecutionRecord["graph_structure"],
        runtime_state: {
          quality_gates: [
            {
              gate_id: "citation_ready",
              status: "pass",
              severity: "low",
            },
            {
              gate_id: "citation_ready",
              status: "warning",
              severity: "medium",
              next_action: "补齐引用元数据",
            },
            {
              gate_id: "evidence_traceability",
              status: "warning",
              severity: "medium",
            },
          ],
        },
      }),
    );

    expect(view.team?.qualityGates).toEqual([
      {
        id: "citation_ready",
        status: "warning",
        severity: "medium",
        nextAction: "补齐引用元数据",
      },
      {
        id: "evidence_traceability",
        status: "warning",
        severity: "medium",
        nextAction: null,
      },
    ]);
  });

  it("projects concise quality highlights without raw harness details", () => {
    const view = runViewFromExecution(
      makeExecution({
        runtime_state: {
          quality_gates: [
            {
              gate_id: "citation_strength",
              status: "pass",
              evidence: {
                schema: "wenjin.harness.research_eval.v1",
                strong_count: 2,
                artifact_paths: ["/workspace/tmp/tasks/.harness/outputs/stdout.txt"],
              },
            },
            {
              gate_id: "experiment_interpretation",
              status: "pass",
              evidence: {
                metric_names: ["accuracy"],
                artifact_paths: ["/workspace/outputs/result.json"],
              },
            },
            {
              gate_id: "statistical_robustness",
              status: "pass",
              evidence: {
                sample_size_count: 1,
                passed_robustness_check_count: 2,
              },
            },
            {
              gate_id: "writing_semantic_preservation",
              status: "warning",
              evidence: {
                risky_items: [
                  {
                    file_path: "main.tex",
                    failed_flags: ["citations"],
                    raw: "wenjin.prism.semantic_contract.v1",
                  },
                ],
              },
            },
          ],
        },
      }),
    );

    expect(view.qualityHighlights).toEqual([
      { label: "引用支撑", status: "pass", detail: "2 条强支撑" },
      { label: "实验解释", status: "pass", detail: "指标、限制与产物已对齐" },
      { label: "统计稳健", status: "pass", detail: "方法、样本量与稳健性已检查" },
      { label: "语义保持", status: "warning", detail: "1 处改写需要确认" },
    ]);
    expect(JSON.stringify(view.qualityHighlights)).not.toContain("wenjin.");
    expect(JSON.stringify(view.qualityHighlights)).not.toContain("/workspace/tmp/tasks");
    expect(JSON.stringify(view.qualityHighlights)).not.toContain("stdout");
  });

  it("projects team harness activity without exposing raw tool payload by default", () => {
    const record = makeExecution({
      graph_structure: {
        mode: "team_kernel",
        nodes: [
          {
            id: "team_prepare",
            type: "control",
            phase: "team_kernel",
            task: "prepare_context",
            label: "准备上下文",
          },
          {
            id: "team_recruit",
            type: "control",
            phase: "team_kernel",
            task: "recruit_members",
            label: "组建团队",
          },
          {
            id: "team_dispatch",
            type: "team",
            phase: "team_kernel",
            task: "dispatch_invocations",
            label: "成员执行",
          },
        ],
        edges: [],
      } as ExecutionRecord["graph_structure"],
      node_states: {
        "team.1.evidence_analyst_v1.1": {
          status: "completed",
          node_type: "agent_invocation",
          label: "实验分析工程师",
          tool_calls: [
            {
              name: "sandbox.run_python",
              status: "completed",
              args: {
                script: "print('raw script should stay technical')",
              },
              result_preview: "stdout: raw output should stay hidden",
            },
          ],
          node_metadata: {
            team: true,
            template_id: "evidence_analyst.v1",
            display_name: "实验分析工程师",
            effective_tools: ["sandbox.run_python"],
            effective_skills: ["evidence-analyst"],
            harness: {
              run_journal_summary: {
                schema: "wenjin.harness.run_journal_summary.v1",
                latest_phase: "tool_completed",
                summary: "实验分析工程师完成实验并生成 1 个产物",
                tool_call_count: 1,
                artifact_count: 1,
              },
              sandbox_execution_summary: {
                schema: "wenjin.harness.sandbox_execution_summary.v1",
                python_runs: 1,
                failed_python_runs: 0,
                recoverable_failures: 0,
                sandbox_job_ids: ["job-1"],
                sandbox_environment_ids: ["env-1"],
                failure_codes: [],
                generated_artifact_count: 1,
              },
            },
          },
        },
      } as ExecutionRecord["node_states"],
    });

    const view = runViewFromExecution(record);
    const progressItems = buildRunProgressItems(record);

    expect(view.team?.members[0]?.displayName).toBe("实验分析工程师");
    expect(view.team?.members[0]?.activityLabel).toBe("实验分析工程师完成实验并生成 1 个产物");
    expect(view.team?.members[0]?.artifactCount).toBe(1);
    expect(view.team?.members[0]?.debugToolCount).toBe(1);
    expect(progressItems.find((item) => item.id === "team_dispatch")?.detail).toBe("1/1 个成员完成");
    expect(JSON.stringify(view.team?.members[0])).not.toContain("raw output");
    expect(JSON.stringify(progressItems[0])).not.toContain("raw script");
  });

  it("projects reproducibility summary into concise team activity", () => {
    const view = runViewFromExecution(
      makeExecution({
        graph_structure: {
          mode: "team_kernel",
          nodes: [],
          edges: [],
        } as ExecutionRecord["graph_structure"],
        node_states: {
          "experiment_engineer.v1__1": {
            status: "completed",
            node_type: "agent_invocation",
            label: "实验工程师",
            node_metadata: {
              team: true,
              template_id: "experiment_engineer.v1",
              display_name: "实验工程师",
              harness: {
                reproducibility_summary: {
                  schema: "wenjin.harness.reproducibility_summary.v1",
                  python_runs: 1,
                  dataset_paths: ["/workspace/datasets/panel.csv"],
                  artifact_paths: ["/workspace/outputs/result.json"],
                  script_paths: ["/workspace/scripts/analysis.py"],
                  next_actions: ["检查稳健性"],
                },
              },
            },
          },
        } as ExecutionRecord["node_states"],
      }),
    );

    expect(view.team?.members[0]?.activityLabel).toBe(
      "已完成可复现实验：1 个脚本 · 1 个数据集 · 1 个产物",
    );
    expect(view.team?.members[0]?.artifactCount).toBe(1);
  });

  it("humanizes technical graph nodes for the default run progress view", () => {
    const progressItems = buildRunProgressItems(
      makeExecution({
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
          },
        },
      }),
    );

    expect(progressItems[0]).toMatchObject({
      id: "step_02_literature_synthesizer",
      title: "文献综合专家",
      phaseTitle: "文献综合",
      technicalName: "step_02_literature_synthesizer",
    });
    expect(progressItems[0].title).not.toContain("literature_synthesizer");
    expect(progressItems[0].phaseTitle).not.toBe("synthesis");
  });

  it("derives team kernel progress from real team work instead of template placeholders", () => {
    const record = makeExecution({
      status: "failed_partial",
      progress: 80,
      graph_structure: {
        mode: "team_kernel",
        nodes: [
          {
            id: "team_prepare",
            type: "control",
            phase: "team_kernel",
            task: "prepare_context",
            label: "准备上下文",
          },
          {
            id: "team_recruit",
            type: "control",
            phase: "team_kernel",
            task: "recruit_members",
            label: "组建团队",
          },
          {
            id: "team_dispatch",
            type: "team",
            phase: "team_kernel",
            task: "dispatch_invocations",
            label: "成员执行",
          },
          {
            id: "team_quality_gate",
            type: "quality_gate",
            phase: "team_kernel",
            task: "quality_gate",
            label: "质量闭环",
          },
          {
            id: "team_finish",
            type: "control",
            phase: "team_kernel",
            task: "finish",
            label: "整理结果",
          },
          {
            id: "team_template_1",
            type: "agent_template",
            phase: "team_members",
            task: "literature_synthesizer.v1",
            label: "literature_synthesizer.v1",
          },
        ],
        edges: [],
      } as ExecutionRecord["graph_structure"],
      node_states: {
        "research_scout.v1__1": {
          status: "completed",
          node_type: "agent_invocation",
          node_metadata: {
            team: true,
            template_id: "research_scout.v1",
            display_name: "文献检索员",
          },
        },
        "literature_synthesizer.v1__1": {
          status: "failed",
          node_type: "agent_invocation",
          node_metadata: {
            team: true,
            template_id: "literature_synthesizer.v1",
            display_name: "文献综合专家",
          },
        },
      } as ExecutionRecord["node_states"],
      runtime_state: {
        quality_gates: [
          {
            gate_id: "citation_ready",
            status: "warning",
            severity: "medium",
          },
        ],
      },
      result: {
        task_report: {
          review_items: [{ id: "result-1", kind: "document", title: "文献定位与创新点.md" }],
        },
      },
    });

    const progressItems = buildRunProgressItems(record);
    const view = runViewFromExecution(record);

    expect(progressItems.map((item) => item.id)).toEqual([
      "team_prepare",
      "team_recruit",
      "team_dispatch",
      "team_quality_gate",
      "team_finish",
    ]);
    expect(progressItems.map((item) => item.title)).not.toContain("工作步骤");
    expect(progressItems.map((item) => item.status)).toEqual([
      "completed",
      "completed",
      "failed_partial",
      "failed_partial",
      "completed",
    ]);
    expect(view.nodeCount).toBe(5);
    expect(view.completedNodeCount).toBe(3);
  });

  it("uses user-facing team names when metadata only has a template id", () => {
    const view = runViewFromExecution(
      makeExecution({
        graph_structure: {
          mode: "team_kernel",
          nodes: [],
          edges: [],
        } as ExecutionRecord["graph_structure"],
        node_states: {
          "literature_synthesizer.v1__1": {
            status: "running",
            node_type: "agent_invocation",
            node_metadata: {
              team: true,
              template_id: "literature_synthesizer.v1",
            },
          },
          "research_scholar.v1__1": {
            status: "pending",
            node_type: "agent_invocation",
            node_metadata: {
              team: true,
              template_id: "research_scholar.v1",
            },
          },
        } as ExecutionRecord["node_states"],
      }),
    );

    expect(view.team?.members[0]?.displayName).toBe("文献综合专家");
    expect(view.team?.members[0]?.displayName).not.toContain("literature_synthesizer");
    expect(view.team?.members[1]?.displayName).toBe("文献专家");
    expect(view.team?.members[1]?.displayName).not.toContain("research_scholar");
  });

  it("orders team members by graph node order instead of node state key order", () => {
    const view = runViewFromExecution(
      makeExecution({
        graph_structure: {
          mode: "team_kernel",
          nodes: [
            {
              id: "step_01_research_scholar",
              type: "agent_invocation",
              task: "research_scholar",
            },
            {
              id: "step_02_literature_synthesizer",
              type: "agent_invocation",
              task: "literature_synthesizer",
            },
            {
              id: "step_03_quality_reviewer",
              type: "agent_invocation",
              task: "quality_reviewer",
            },
          ],
          edges: [],
        } as ExecutionRecord["graph_structure"],
        node_states: {
          step_03_quality_reviewer: {
            status: "pending",
            node_type: "agent_invocation",
            node_metadata: {
              team: true,
              template_id: "quality_reviewer.v1",
            },
          },
          step_01_research_scholar: {
            status: "completed",
            node_type: "agent_invocation",
            node_metadata: {
              team: true,
              template_id: "research_scholar.v1",
            },
          },
          step_02_literature_synthesizer: {
            status: "running",
            node_type: "agent_invocation",
            node_metadata: {
              team: true,
              template_id: "literature_synthesizer.v1",
            },
          },
        } as ExecutionRecord["node_states"],
      }),
    );

    expect(view.team?.members.map((member) => member.displayName)).toEqual([
      "文献专家",
      "文献综合专家",
      "质量风险专家",
    ]);
  });

  it("projects historical run records", () => {
    const view = runViewFromRunRecord(
      {
        id: "run-1",
        workspace_id: "ws-1",
        capability_id: "cap-1",
        capability_name: "论文研究包",
        status: "completed",
        started_at: "2026-05-22T00:00:00Z",
        completed_at: "2026-05-22T00:01:00Z",
        summary: "done",
        token_usage: { input: 1, output: 2 },
        has_prism_changes: true,
        review_items_count: 2,
      },
      "ws-1",
    );

    expect(view.title).toBe("论文研究包");
    expect(view.durationLabel).toBe("1m");
    expect(view.prismReviewCount).toBe(2);
    expect(view.actions).toContain("open_prism");
  });

  it("projects chat result cards", () => {
    const view = runViewFromResultCard(
      {
        execution_id: "exec-1",
        capability_name: "文献定位与创新点",
        status: "completed",
        outputs: [],
        review_items: [
          {
            id: "review-1",
            kind: "prism_file_change",
            logical_key: "section:intro",
            status: "pending",
            title: "Intro",
          },
        ],
        narrative: "完成",
        duration_seconds: 43,
      },
      "ws-1",
    );

    expect(view.status).toBe("completed");
    expect(view.durationLabel).toBe("43s");
    expect(view.hasPrismChanges).toBe(true);
  });

  it("merges live and historical views without losing actions", () => {
    const live = runViewFromExecution(makeExecution({ status: "running" }));
    const historical = runViewFromRunRecord(
      {
        id: "exec-1",
        capability_name: "文献定位与创新点",
        status: "completed",
        started_at: "2026-05-22T00:00:00Z",
        completed_at: "2026-05-22T00:00:30Z",
        summary: "done",
        has_prism_changes: true,
      },
      "ws-1",
    );

    const merged = mergeRunViews(live, historical);
    expect(merged.status).toBe("running");
    expect(merged.hasPrismChanges).toBe(true);
    expect(merged.actions).toContain("open_prism");
  });
});
