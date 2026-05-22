import { describe, expect, it } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import {
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
