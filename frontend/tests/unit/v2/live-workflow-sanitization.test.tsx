import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import { CompletedView } from "@/app/(workbench)/workspaces/[id]/components/CompletedView";
import { NodeInspector } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/NodeInspector";
import {
  buildEvidenceItems,
  buildSandboxSummary,
} from "@/app/(workbench)/workspaces/[id]/components/live-workflow/utils";
import { buildWorkspaceResultPreviewsFromOutputs } from "@/lib/workspace-result-preview";

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

describe("live workflow sanitization", () => {
  it("summarizes sandbox output refs without raw streams or internal harness paths", () => {
    const summary = buildSandboxSummary({
      status: "completed",
      output: {
        operation: "python_script",
        status: "completed",
        exit_code: 0,
        docker_image: "python:3.13",
        stdout: "raw stdout should stay hidden",
        stderr: "raw stderr should stay hidden",
        output_refs: [
          "/workspace/outputs/figures/result.png",
          "/workspace/outputs/harness/exec-1/node/raw-stdout.txt",
        ],
      },
    });

    const text = summary?.join(" · ") ?? "";
    expect(text).toContain("操作：python_script");
    expect(text).toContain("2 个可恢复引用");
    expect(text).not.toContain("stdout");
    expect(text).not.toContain("stderr");
    expect(text).not.toContain("raw stdout should stay hidden");
    expect(text).not.toContain("raw stderr should stay hidden");
    expect(text).not.toContain("/workspace/outputs/harness");
  });

  it("builds evidence summaries without falling back to raw JSON output", () => {
    const record = baseRecord({
      id: "evidence-raw-1",
      graph_structure: {
        mode: "team_kernel",
        nodes: [{ id: "writer", type: "agent_invocation", label: "写作专家" }],
        edges: [],
      },
      node_states: {
        writer: {
          status: "completed",
          output: {
            status: "completed",
            result: {
              stdout: "raw stdout should stay hidden",
              stderr: "raw stderr should stay hidden",
            },
            internal_ref: "/workspace/outputs/harness/exec-1/node/raw.json",
          },
        },
      },
    });

    const [item] = buildEvidenceItems(record, []);

    expect(item?.summary).toContain("运行记录已更新");
    expect(item?.summary).not.toContain("stdout");
    expect(item?.summary).not.toContain("stderr");
    expect(item?.summary).not.toContain("raw stdout should stay hidden");
    expect(item?.summary).not.toContain("/workspace/outputs/harness");
    expect(item?.summary).not.toContain("{");
  });

  it("keeps NodeInspector details product-safe by omitting raw input and output panes", () => {
    render(
      <NodeInspector
        node={{ id: "sandbox-node", type: "agent_invocation", label: "实验步骤" }}
        state={{
          status: "completed",
          started_at: "2026-05-18T00:00:00Z",
          input: {
            prompt: "raw input should stay hidden",
          },
          output: {
            operation: "python_script",
            status: "completed",
            stdout: "raw stdout should stay hidden",
            stderr: "raw stderr should stay hidden",
            output_refs: ["/workspace/outputs/harness/exec-1/node/raw.txt"],
          },
          tool_calls: [
            {
              name: "sandbox.run_python",
              status: "completed",
              exit_code: 0,
              docker_image: "python:3.13",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("技术详情")).toBeInTheDocument();
    expect(screen.getByText("sandbox-node")).toBeInTheDocument();
    expect(screen.getByText("sandbox.run_python")).toBeInTheDocument();
    expect(screen.getByText(/可恢复引用/)).toBeInTheDocument();
    expect(screen.queryByText("输入预览")).not.toBeInTheDocument();
    expect(screen.queryByText("输出预览")).not.toBeInTheDocument();
    expect(screen.queryByText(/raw input should stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw stdout should stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw stderr should stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/workspace\/outputs\/harness/)).not.toBeInTheDocument();
  });

  it("sanitizes NodeInspector progress thinking summaries", () => {
    render(
      <NodeInspector
        node={{ id: "thinking-node", type: "agent_invocation", label: "思考步骤" }}
        state={{
          status: "running",
          thinking:
            '{"stdout":"raw stdout should stay hidden","ref":"/workspace/outputs/harness/exec-1/thinking.txt"}',
        }}
      />,
    );

    expect(screen.getByText("当前步骤暂无详细摘要。")).toBeInTheDocument();
    expect(screen.queryByText(/stdout/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw stdout should stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/workspace\/outputs\/harness/)).not.toBeInTheDocument();
  });

  it("renders a safe completed result fallback instead of a raw JSON toggle", () => {
    render(
      <CompletedView
        result={{
          status: "completed",
          stdout: "raw stdout should stay hidden",
          stderr: "raw stderr should stay hidden",
          output_ref: "/workspace/outputs/harness/exec-1/result.json",
        }}
      />,
    );

    expect(screen.getByText("运行结果已生成。")).toBeInTheDocument();
    expect(screen.getByText("状态：已完成")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /view full result/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/raw stdout should stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw stderr should stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/workspace\/outputs\/harness/)).not.toBeInTheDocument();
  });

  it("sanitizes completed task errors before rendering them", () => {
    render(
      <CompletedView
        result={{
          task_report: {
            status: "failed_partial",
            narrative: "Run partially completed.",
            outputs: [],
            errors: [
              {
                phase: "analysis",
                task: "sandbox",
                error:
                  '{"stderr":"raw stderr should stay hidden","ref":"/workspace/outputs/harness/exec-1/error.txt"}',
              },
            ],
          },
        }}
      />,
    );

    expect(screen.getByText("需处理事项：1 项")).toBeInTheDocument();
    expect(screen.getByText(/问题 1/)).toBeInTheDocument();
    expect(screen.getByText(/运行问题已记录/)).toBeInTheDocument();
    expect(screen.queryByText(/stderr/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw stderr should stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/workspace\/outputs\/harness/)).not.toBeInTheDocument();
  });

  it("uses safe staged-output fallback previews instead of raw JSON", () => {
    const previews = buildWorkspaceResultPreviewsFromOutputs([
      {
        id: "memory-1",
        kind: "memory_fact",
        data: {
          stdout: "raw stdout should stay hidden",
          ref: "/workspace/outputs/harness/exec-1/memory.json",
        },
      },
      {
        id: "decision-1",
        kind: "decision",
        data: {
          stderr: "raw stderr should stay hidden",
          ref: "/workspace/outputs/harness/exec-1/decision.json",
        },
      },
      {
        id: "task-1",
        kind: "task",
        data: {
          stdout: "raw stdout should stay hidden",
          ref: "/workspace/outputs/harness/exec-1/task.json",
        },
      },
    ]);

    expect(previews).toHaveLength(3);
    const text = previews.map((preview) => preview.previewText).join("\n");
    expect(text).toContain("已生成记忆片段");
    expect(text).toContain("已生成决策记录");
    expect(text).toContain("已生成任务项");
    expect(text).toContain("字段：2 项");
    expect(text).not.toContain("stdout");
    expect(text).not.toContain("stderr");
    expect(text).not.toContain("raw stdout should stay hidden");
    expect(text).not.toContain("raw stderr should stay hidden");
    expect(text).not.toContain("/workspace/outputs/harness");
    expect(text).not.toContain("{");
  });
});
