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
