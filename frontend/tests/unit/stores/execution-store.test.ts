import { beforeEach, describe, expect, it } from "vitest";

import type { ExecutionRecord, ExecutionStreamEvent } from "@/lib/api/types";
import { useExecutionStore } from "@/stores/execution-store";

const makeRecord = (
  overrides: Partial<ExecutionRecord> = {},
): ExecutionRecord => ({
  id: "exec-1",
  user_id: "u1",
  execution_type: "feature",
  status: "running",
  params: {},
  node_states: {},
  artifact_ids: [],
  next_actions: [],
  child_execution_ids: [],
  progress: 0,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

const makeEvent = (
  overrides: Partial<ExecutionStreamEvent> = {},
): ExecutionStreamEvent => ({
  execution_id: "exec-1",
  type: "execution.status",
  timestamp: "2026-01-01T00:00:01Z",
  payload: {},
  ...overrides,
});

beforeEach(() => {
  useExecutionStore.getState().clear();
});

describe("execution-store", () => {
  it("uses execution.completed payload status and keeps failed_partial terminal", () => {
    useExecutionStore.getState().upsertExecution(makeRecord());

    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.completed",
        payload: {
          execution_id: "exec-1",
          capability_id: "lit_review",
          status: "failed_partial",
          duration_seconds: 12,
          narrative: "Completed with one failed node.",
          outputs: [
            {
              id: "paper-1",
              kind: "library_item",
              preview: "Paper preview",
              default_checked: true,
              data: { title: "Paper" },
            },
          ],
          errors: [{ phase: "search", task: "api", error: "429" }],
        },
      }),
    );

    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.end",
        timestamp: "2026-01-01T00:00:02Z",
      }),
    );

    const record = useExecutionStore.getState().executions.get("exec-1");
    expect(record?.status).toBe("failed_partial");
    expect(record?.result_summary).toBe("Completed with one failed node.");
    expect(record?.result?.outputs).toHaveLength(1);
  });

  it("appends thinking deltas instead of replacing them", () => {
    useExecutionStore.getState().upsertExecution(makeRecord());

    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.node",
        payload: { node_id: "node-1", status: "running" },
      }),
    );
    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.node.delta",
        payload: { node_id: "node-1", thinking: "hello " },
      }),
    );
    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.node.delta",
        payload: { node_id: "node-1", thinking: "world" },
      }),
    );

    const record = useExecutionStore.getState().executions.get("exec-1");
    expect(record?.node_states["node-1"]?.status).toBe("running");
    expect(record?.node_states["node-1"]?.thinking).toBe("hello world");
  });

  it("applies canonical execution.node status updates", () => {
    useExecutionStore.getState().upsertExecution(makeRecord());

    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.node",
        payload: { node_id: "node-1", status: "completed" },
      }),
    );

    const record = useExecutionStore.getState().executions.get("exec-1");
    expect(record?.node_states["node-1"]?.status).toBe("completed");
  });

  it("merges node input, output, tool calls, and timestamps from completed events", () => {
    useExecutionStore.getState().upsertExecution(makeRecord());

    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.node",
        payload: {
          node_id: "node-1",
          status: "completed",
          input_data: { query: "sandbox smoke" },
          output_data: { exit_code: 0, stdout: "ok" },
          tool_calls: [{ name: "sandbox.run_python", status: "completed" }],
          started_at: "2026-01-01T00:00:01Z",
          completed_at: "2026-01-01T00:00:03Z",
        },
      }),
    );

    const node = useExecutionStore.getState().executions.get("exec-1")
      ?.node_states["node-1"];
    expect(node?.input).toEqual({ query: "sandbox smoke" });
    expect(node?.output).toEqual({ exit_code: 0, stdout: "ok" });
    expect(node?.tool_calls).toEqual([
      { name: "sandbox.run_python", status: "completed" },
    ]);
    expect(node?.completed_at).toBe("2026-01-01T00:00:03Z");
  });

  it("applies team invocation and quality gate stream events", () => {
    useExecutionStore.getState().upsertExecution(
      makeRecord({
        graph_structure: {
          mode: "team_kernel",
          nodes: [],
          edges: [],
        },
      }),
    );

    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.team.invocation",
        payload: {
          invocation: {
            id: "team.1.research_scholar_v1.1",
            template_id: "research_scholar.v1",
            display_name: "文献专家",
            assigned_role: "文献专家",
            recruitment_reason: "core team member",
            status: "running",
            effective_tools: ["web_search", "library_read"],
            effective_skills: ["research-scout"],
            input_brief: { topic: "LLM evidence" },
          },
        },
      }),
    );
    useExecutionStore.getState().applyStreamEvent(
      makeEvent({
        type: "execution.team.quality_gate",
        payload: {
          quality_gate: {
            gate_id: "evidence_traceability",
            status: "warning",
            severity: "medium",
            next_action: "revise_existing",
          },
        },
      }),
    );

    const record = useExecutionStore.getState().executions.get("exec-1");
    expect(record?.graph_structure?.mode).toBe("team_kernel");
    expect(record?.node_states["team.1.research_scholar_v1.1"]).toMatchObject({
      status: "running",
      node_type: "agent_invocation",
      label: "文献专家",
      input: { topic: "LLM evidence" },
      node_metadata: {
        team: true,
        template_id: "research_scholar.v1",
        display_name: "文献专家",
        effective_tools: ["web_search", "library_read"],
        effective_skills: ["research-scout"],
      },
    });
    expect(record?.runtime_state?.quality_gates).toEqual([
      {
        gate_id: "evidence_traceability",
        status: "warning",
        severity: "medium",
        next_action: "revise_existing",
      },
    ]);
  });
});
