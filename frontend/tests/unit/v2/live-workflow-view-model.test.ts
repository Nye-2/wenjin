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
      draftEdits: {},
    });

    expect(model.selectedRecord?.id).toBe("sandbox-1");
    expect(model.pendingReviewCount).toBe(0);
    expect(model.sandboxCount).toBe(1);
    expect(model.evidenceItems).toHaveLength(1);
    expect(model.evidenceItems[0]?.summary).toContain("输出：已生成");
    expect(model.evidenceItems[0]?.summary).not.toContain("stdout");
    expect(model.evidenceItems[0]?.summary).not.toContain("ok");
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
      draftEdits: {},
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
      draftEdits: {},
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
      draftEdits: {},
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
      draftEdits: {},
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
      draftEdits: {},
    });

    expect(model.selectedRecord?.id).toBe("run-2");
    expect(model.runningRecord?.id).toBe("run-2");
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
});
