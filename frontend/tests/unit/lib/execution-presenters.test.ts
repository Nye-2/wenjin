import { describe, expect, it } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import {
  adaptExecutionToPanelSession,
  buildExecutionCurrentTask,
  groupExecutionPanels,
  selectPreferredExecution,
} from "@/lib/execution-presenters";

const makeExecution = (
  overrides: Partial<ExecutionRecord> = {},
): ExecutionRecord => ({
  id: "exec-1",
  user_id: "user-1",
  workspace_id: "ws-1",
  execution_type: "feature",
  feature_id: "lit_review",
  display_name: "文献检索",
  status: "running",
  params: {},
  node_states: {},
  artifact_ids: [],
  next_actions: [],
  child_execution_ids: [],
  progress: 40,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:10Z",
  ...overrides,
});

describe("execution-presenters", () => {
  it("prefers active execution records", () => {
    const completed = makeExecution({
      id: "exec-done",
      status: "completed",
      created_at: "2026-01-01T00:00:00Z",
    });
    const running = makeExecution({
      id: "exec-live",
      status: "running",
      created_at: "2026-01-01T00:00:01Z",
    });

    expect(selectPreferredExecution([completed, running])?.id).toBe("exec-live");
  });

  it("builds current task stages from graph nodes", () => {
    const execution = makeExecution({
      graph_structure: {
        nodes: [
          { id: "n1", type: "skill", label: "检索" },
          { id: "n2", type: "skill", label: "整理" },
        ],
        edges: [],
      },
      node_states: {
        n1: { status: "completed" },
        n2: { status: "running" },
      },
    });

    const task = buildExecutionCurrentTask(execution, undefined);
    expect(task.stages).toEqual([
      { id: "n1", label: "检索", status: "completed" },
      { id: "n2", label: "整理", status: "running" },
    ]);
    expect(task.currentStageIndex).toBe(1);
  });

  it("adapts execution record to panel session", () => {
    const execution = makeExecution({
      message: "正在检索",
      graph_structure: {
        nodes: [
          { id: "n1", type: "skill", label: "检索", phase: "research", subagent_type: "searcher" },
        ],
        edges: [],
      },
      node_states: {
        n1: {
          status: "running",
          output_preview: "preview",
          token_usage: { input_tokens: 10, output_tokens: 5, total_tokens: 15 },
        },
      },
    });

    const session = adaptExecutionToPanelSession(execution, null);
    expect(session.executionId).toBe("exec-1");
    expect(session.status).toBe("running");
    expect(session.subagents).toHaveLength(1);
    expect(session.tokenUsage?.total_tokens).toBe(15);
  });

  it("groups active and completed panel sessions", () => {
    const active = adaptExecutionToPanelSession(
      makeExecution({ id: "exec-live", status: "running" }),
      null,
    );
    const completed = adaptExecutionToPanelSession(
      makeExecution({ id: "exec-done", status: "completed" }),
      null,
    );

    const grouped = groupExecutionPanels([completed, active]);
    expect(grouped.active.map((item) => item.executionId)).toEqual(["exec-live"]);
    expect(grouped.recent.map((item) => item.executionId)).toEqual(["exec-done"]);
  });
});
