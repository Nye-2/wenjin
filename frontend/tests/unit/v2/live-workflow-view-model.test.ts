import { describe, expect, it } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import type { WorkspaceResultPreview } from "@/lib/workspace-result-preview";
import {
  buildLiveWorkflowViewModel,
  resolveAutoWorkbenchTab,
  selectLiveWorkflowRecords,
} from "@/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel";

function baseRecord(overrides: Partial<ExecutionRecord>): ExecutionRecord {
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
    result: null,
    ...overrides,
  };
}

const runningRecord = baseRecord({
  id: "run-1",
  status: "running",
  progress: 30,
  completed_at: null,
  created_at: "2026-05-18T00:00:01Z",
});

const completedRecord = baseRecord({
  id: "done-1",
  status: "completed",
  result: {
    task_report: {
      outputs: [
        {
          id: "doc-1",
          kind: "document",
          preview: "Outline",
          default_checked: true,
          data: { name: "outline.md", content: "# Outline" },
        },
      ],
    },
  },
});

const changeSetOnlyRecord = baseRecord({
  id: "changes-1",
  status: "completed",
  result: {
    change_set: {
      execution_id: "changes-1",
      workspace_id: "ws-1",
      write_mode: "strict_review",
      summary: "Review one workspace write.",
      created_at: "2026-06-13T00:00:00Z",
      units: [
        {
          id: "unit-doc-1",
          target: {
            room: "documents",
            object_type: "document",
            object_id: "doc-1",
            path: "draft.md",
          },
          action: "write_document_draft",
          risk: "high",
          risk_reasons: ["writes research draft"],
          default_apply_state: "blocked",
          requires_confirmation: true,
          diff: { title: "Draft update" },
          provenance: { output_id: "doc-1" },
          rollback: {},
        },
      ],
    },
  },
});

const sandboxRecord = baseRecord({
  id: "sandbox-1",
  status: "completed",
  node_states: {
    "sandbox-node": {
      status: "completed",
      output: {
        operation: "python_script",
        status: "completed",
        exit_code: 0,
        docker_image: "python:3.13",
        stdout: "ok",
      },
    },
  },
});

const preview: WorkspaceResultPreview = {
  id: "doc-1",
  source: "staged_output",
  kind: "document",
  title: "Outline",
  subtitle: "outline.md",
  badge: null,
  previewMode: "markdown",
  previewText: "Outline",
  metadataLines: [],
  defaultChecked: true,
  canCommit: true,
  canOpenRoom: false,
  data: { name: "outline.md" },
};

describe("live workflow view model", () => {
  it("orders active workspace records before terminal history", () => {
    const records = selectLiveWorkflowRecords({
      records: [completedRecord, runningRecord],
      workspaceId: "ws-1",
      activeRunId: null,
    });

    expect(records.map((record) => record.id)).toEqual(["run-1", "done-1"]);
  });

  it("derives review and sandbox counts from the selected execution", () => {
    const model = buildLiveWorkflowViewModel({
      records: [completedRecord, sandboxRecord],
      workspaceId: "ws-1",
      selectedRunId: "sandbox-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });

    expect(model.selectedRecord?.id).toBe("sandbox-1");
    expect(model.pendingReviewCount).toBe(0);
    expect(model.sandboxCount).toBe(1);
    expect(model.evidenceItems).toHaveLength(1);
    expect(model.evidenceItems[0]?.summary).toContain("输出：已生成");
    expect(model.evidenceItems[0]?.summary).not.toContain("stdout");
    expect(model.evidenceItems[0]?.summary).not.toContain("ok");
  });

  it("uses ChangeSet pending units for review focus without legacy previews", () => {
    const model = buildLiveWorkflowViewModel({
      records: [changeSetOnlyRecord],
      workspaceId: "ws-1",
      selectedRunId: "changes-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });

    expect(model.selectedRecord?.id).toBe("changes-1");
    expect(model.previews).toHaveLength(0);
    expect(model.changeSet?.units[0]?.id).toBe("unit-doc-1");
    expect(model.pendingReviewCount).toBe(1);
    expect(
      resolveAutoWorkbenchTab({
        selectedRecord: changeSetOnlyRecord,
        previews: [],
        reviewItems: [],
        evidenceItems: [],
        pendingReviewCount: model.pendingReviewCount,
      }),
    ).toBe("review");
  });

  it("projects harness reproducibility evidence without raw sandbox noise", () => {
    const reproducibleRecord = baseRecord({
      id: "repro-1",
      status: "completed",
      node_states: {
        "experiment-node": {
          status: "completed",
          node_type: "agent_invocation",
          label: "实验工程师",
          output: {
            stdout: "raw stdout should stay hidden",
          },
          node_metadata: {
            harness: {
              reproducibility_summary: {
                schema: "wenjin.harness.reproducibility_summary.v1",
                script_paths: ["/workspace/scripts/analysis.py"],
                dataset_paths: ["/workspace/datasets/panel.csv"],
                artifact_paths: [
                  "/workspace/outputs/result.json",
                  "/workspace/outputs/harness/exec/node/raw.txt",
                ],
                next_actions: ["复核图表"],
              },
            },
          },
        },
      },
    });

    const model = buildLiveWorkflowViewModel({
      records: [reproducibleRecord],
      workspaceId: "ws-1",
      selectedRunId: "repro-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });

    expect(model.evidenceItems).toHaveLength(1);
    expect(model.evidenceItems[0]?.kind).toBe("sandbox");
    expect(model.evidenceItems[0]?.summary).toContain("analysis.py");
    expect(model.evidenceItems[0]?.summary).toContain("panel.csv");
    expect(model.evidenceItems[0]?.summary).toContain("result.json");
    expect(model.evidenceItems[0]?.summary).not.toContain("stdout");
    expect(model.evidenceItems[0]?.summary).not.toContain("/workspace/outputs/harness");
  });

  it("projects citation source audit findings as bounded evidence", () => {
    const citationAuditRecord = baseRecord({
      id: "citation-audit-1",
      status: "failed_partial",
      runtime_state: {
        quality_gates: [
          {
            gate_id: "no_fabricated_citations",
            status: "fail",
            severity: "high",
            findings: [
              {
                invocation_id: "citation_auditor.v1__1",
                template_id: "citation_auditor.v1",
                citation_source_audit: [
                  {
                    schema: "wenjin.quality.citation_source_audit_finding.v1",
                    field: "fabrication_risks",
                    risk: "fabricated",
                    severity: "high",
                    unknown_refs: ["fake2026"],
                    claim: "A fabricated claim that should be bounded.",
                    message: "not found in library",
                    suggested_action: "replace_or_remove_citation",
                  },
                ],
              },
            ],
          },
        ],
      },
    });

    const model = buildLiveWorkflowViewModel({
      records: [citationAuditRecord],
      workspaceId: "ws-1",
      selectedRunId: "citation-audit-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });

    expect(model.evidenceItems).toHaveLength(1);
    expect(model.evidenceItems[0]?.kind).toBe("citation");
    expect(model.evidenceItems[0]?.title).toContain("引文");
    expect(model.evidenceItems[0]?.summary).toContain("fake2026");
    expect(model.evidenceItems[0]?.summary).toContain("not found in library");
    expect(model.evidenceItems[0]?.summary).toContain("替换或删除");
    expect(model.evidenceItems[0]?.summary).not.toContain(
      "wenjin.quality.citation_source_audit_finding.v1",
    );
    expect(model.evidenceItems[0]?.summary).not.toContain("{");
  });

  it("selects the active running execution before a stale selected history run", () => {
    const model = buildLiveWorkflowViewModel({
      records: [completedRecord, runningRecord],
      workspaceId: "ws-1",
      selectedRunId: "done-1",
      focusedRunId: null,
      activeRunId: "run-1",
      selectedPreviewId: null,
    });

    expect(model.selectedRecord?.id).toBe("run-1");
    expect(model.runningRecord?.id).toBe("run-1");
  });

  it("keeps a newly active terminal execution visible after it finishes quickly", () => {
    const fastFinishedRecord = baseRecord({
      id: "fast-1",
      status: "failed_partial",
      progress: 0,
      completed_at: "2026-05-18T00:00:04Z",
      created_at: "2026-05-18T00:00:03Z",
    });

    const model = buildLiveWorkflowViewModel({
      records: [completedRecord, fastFinishedRecord],
      workspaceId: "ws-1",
      selectedRunId: "done-1",
      focusedRunId: null,
      activeRunId: "fast-1",
      selectedPreviewId: null,
    });

    expect(model.selectedRecord?.id).toBe("fast-1");
    expect(model.runningRecord).toBeNull();
  });

  it("keeps a newly running execution visible even when persisted selection is stale", () => {
    const newRunningRecord = baseRecord({
      id: "run-2",
      status: "running",
      progress: 5,
      completed_at: null,
      created_at: "2026-05-18T00:00:03Z",
    });

    const model = buildLiveWorkflowViewModel({
      records: [completedRecord, newRunningRecord],
      workspaceId: "ws-1",
      selectedRunId: "done-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });

    expect(model.selectedRecord?.id).toBe("run-2");
    expect(model.runningRecord?.id).toBe("run-2");
  });

  it("surfaces claim and citation risks as evidence items", () => {
    const riskyRecord = baseRecord({
      id: "risk-1",
      status: "completed",
      runtime_state: {
        quality_gates: [
          {
            gate_id: "evidence_contract_integrity",
            status: "fail",
            severity: "high",
          },
        ],
      },
      result: {
        task_report: {
          outputs: [
            {
              id: "doc-1",
              kind: "document",
              preview: "Draft with an unsupported claim",
              default_checked: true,
              data: {
                name: "draft.md",
                content: "Claim A needs support.",
              },
            },
          ],
        },
      },
      node_states: {
        reviewer: {
          status: "completed",
          output: {
            claim_evidence_map: [
              {
                claim_id: "c1",
                claim_text: "Claim A needs support.",
                status: "unsupported",
                evidence_refs: [
                  {
                    ref_type: "library",
                    ref_id: "paper-1",
                    citation_key: "smith2025",
                  },
                ],
                citation_keys: ["smith2025"],
                required_fix: "Add a verified source before committing.",
              },
            ],
            citation_key_audit: [
              {
                claim_id: "c1",
                citation_key: "smith2025",
                status: "unsupported",
                evidence_refs: [{ ref_type: "library", ref_id: "paper-1" }],
              },
            ],
            fabrication_risks: [
              {
                citation_key: "ghost2024",
                risk: "Citation key is not present in Library.",
                required_fix: "Remove or replace with a verified source.",
              },
            ],
          },
        },
      },
    });

    const model = buildLiveWorkflowViewModel({
      records: [riskyRecord],
      workspaceId: "ws-1",
      selectedRunId: "risk-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });

    expect(model.previews.map((item) => item.id)).toContain("doc-1");
    expect(model.previews.find((item) => item.id === "doc-1")?.defaultChecked).toBe(true);
    expect(
      model.evidenceItems.find((item) => item.source === "claim")?.citationKeys,
    ).toEqual(["smith2025"]);
    expect(
      model.evidenceItems.find((item) => item.source === "citation")?.riskLevel,
    ).toBe("high");
  });

  it("moves completed runs with outputs to review and running runs to run tab", () => {
    expect(
      resolveAutoWorkbenchTab({
        selectedRecord: runningRecord,
        previews: [],
        reviewItems: [],
        evidenceItems: [],
      }),
    ).toBe("run");
    expect(
      resolveAutoWorkbenchTab({
        selectedRecord: completedRecord,
        previews: [preview],
        reviewItems: [],
        evidenceItems: [],
      }),
    ).toBe("review");
  });

  it("reports no mission activity when there are no records", () => {
    const model = buildLiveWorkflowViewModel({
      records: [],
      workspaceId: "ws-1",
      selectedRunId: null,
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });

    expect(model.selectedRunView).toBeNull();
    expect(model.hasMissionActivity).toBe(false);
  });

  it("reports mission activity for active, review, evidence, and selected completed runs", () => {
    const activeModel = buildLiveWorkflowViewModel({
      records: [runningRecord],
      workspaceId: "ws-1",
      selectedRunId: "run-1",
      focusedRunId: null,
      activeRunId: "run-1",
      selectedPreviewId: null,
    });
    expect(activeModel.hasMissionActivity).toBe(true);
    expect(activeModel.selectedRunView?.mission).not.toBeNull();

    const reviewModel = buildLiveWorkflowViewModel({
      records: [changeSetOnlyRecord],
      workspaceId: "ws-1",
      selectedRunId: "changes-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });
    expect(reviewModel.pendingReviewCount).toBeGreaterThan(0);
    expect(reviewModel.hasMissionActivity).toBe(true);

    const evidenceModel = buildLiveWorkflowViewModel({
      records: [sandboxRecord],
      workspaceId: "ws-1",
      selectedRunId: "sandbox-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });
    expect(evidenceModel.evidenceItems).toHaveLength(1);
    expect(evidenceModel.hasMissionActivity).toBe(true);

    const completedModel = buildLiveWorkflowViewModel({
      records: [completedRecord],
      workspaceId: "ws-1",
      selectedRunId: "done-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });
    expect(completedModel.selectedRunView?.mission).not.toBeNull();
    expect(completedModel.hasMissionActivity).toBe(true);
  });

  it("keeps review as the auto tab when pending review exists alongside evidence", () => {
    const model = buildLiveWorkflowViewModel({
      records: [completedRecord, sandboxRecord],
      workspaceId: "ws-1",
      selectedRunId: "done-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });

    expect(
      resolveAutoWorkbenchTab({
        selectedRecord: model.selectedRecord,
        previews: model.previews,
        reviewItems: model.reviewItems,
        evidenceItems: model.evidenceItems,
        pendingReviewCount: model.pendingReviewCount,
      }),
    ).toBe("review");
  });

  it("projects sandbox figure review items into the review preview list", () => {
    const record = baseRecord({
      id: "figure-review-1",
      status: "completed",
      review_items: [
        {
          id: "review-figure-1",
          kind: "sandbox_artifact",
          status: "pending",
          title: "Accept sandbox artifact: figure",
          summary: "/workspace/outputs/figures/fed_curve/figure.png",
          target: {
            kind: "sandbox_artifact",
            path: "/workspace/outputs/figures/fed_curve/figure.png",
            artifact_kind: "figure",
            sandbox_artifact_id: "artifact-1",
          },
          preview: {
            mode: "artifact",
            path: "/workspace/outputs/figures/fed_curve/figure.png",
            mime_type: "image/png",
            content_hash: "sha256:figure",
          },
          actions: [
            { action: "accept_sandbox_artifact", label: "保存到结果库" },
            { action: "reject_sandbox_artifact", label: "忽略" },
          ],
        },
      ],
    });

    const model = buildLiveWorkflowViewModel({
      records: [record],
      workspaceId: "ws-1",
      selectedRunId: "figure-review-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });

    expect(model.previews).toHaveLength(1);
    expect(model.previews[0]).toMatchObject({
      id: "review:review-figure-1",
      kind: "figure",
      previewMode: "image",
      previewPath: "/workspace/outputs/figures/fed_curve/figure.png",
      canCommit: false,
    });
    expect(model.pendingReviewCount).toBe(1);
    expect(model.selectedPreview?.kind).toBe("figure");
  });

  it("projects review packet items alongside staged outputs", () => {
    const record = baseRecord({
      id: "packet-run-1",
      status: "failed_partial",
      result: {
        task_report: {
          status: "failed_partial",
          outputs: [
            {
              id: "doc-1",
              kind: "document",
              preview: "文献定位与创新点.md",
              default_checked: false,
              data: { name: "文献定位与创新点.md", content: "# Gap map" },
            },
          ],
          review_packet: {
            packet_id: "packet-1",
            completion_status: "partial",
            items: [
              {
                item_id: "risk-1",
                kind: "warning",
                title: "弱证据或未支持论断",
                summary: "研究问题还缺少直接证据。",
                preview: { format: "text", excerpt: "研究问题还缺少直接证据。" },
                risk: { level: "high", reasons: ["unsupported"] },
                can_commit: false,
              },
            ],
          },
        },
      },
    });

    const model = buildLiveWorkflowViewModel({
      records: [record],
      workspaceId: "ws-1",
      selectedRunId: "packet-run-1",
      focusedRunId: null,
      activeRunId: null,
      selectedPreviewId: null,
    });

    expect(model.previews.map((item) => item.id)).toEqual([
      "doc-1",
      "packet:risk-1",
    ]);
    expect(model.pendingReviewCount).toBe(2);
    expect(model.previews[1]).toMatchObject({
      source: "review_packet",
      kind: "warning",
      canCommit: false,
    });
  });
});
