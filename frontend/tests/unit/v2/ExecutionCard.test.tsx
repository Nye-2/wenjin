import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ExecutionRecord } from "@/lib/api/types";
import { ExecutionCard } from "@/app/(workbench)/workspaces/[id]/components/ExecutionCard";

function makeRecord(
  overrides: Partial<ExecutionRecord> = {},
): ExecutionRecord {
  return {
    id: "exec-1",
    user_id: "user-1",
    workspace_id: "ws-1",
    execution_type: "feature",
    workspace_type: "thesis",
    feature_id: "thesis_writing",
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
    ...overrides,
  };
}

describe("ExecutionCard", () => {
  it("surfaces Prism review actions and changed files for completed executions", () => {
    render(
      <ExecutionCard
        record={makeRecord({
          result_summary: "写作结果已进入 Prism 待复核区",
          result: {
            data: {
              latex_project_id: "latex-1",
            },
          },
          review_items: [
            {
              id: "review-1",
              kind: "prism_file_change",
              logical_key: "section:introduction",
              status: "pending",
              title: "Intro rewrite",
              summary: "feature_proposal",
              target: {
                kind: "prism_file_change",
                file_path: "sections/introduction.tex",
              },
            },
          ],
          next_actions: [
            {
              action: "preview_prism_changes",
              label: "预览待复核修改",
              project_id: "latex-1",
              review_item_id: "review-1",
              logical_key: "section:introduction",
            },
            {
              action: "open_prism",
              label: "在 WenjinPrism 中继续编辑",
            },
          ],
        })}
        phases={[]}
        isExpanded
        onToggle={() => {}}
        selectedNodeId={null}
        selectNode={() => {}}
      />,
    );

    expect(screen.getByText("写作结果已进入 Prism 待复核区")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "预览待复核修改" }),
    ).toHaveAttribute(
      "href",
      "/workspaces/ws-1/prism?focus=file_changes&review_item_id=review-1&logical_key=section%3Aintroduction",
    );
    expect(
      screen.getByRole("link", { name: "在 WenjinPrism 中继续编辑" }),
    ).toHaveAttribute("href", "/workspaces/ws-1/prism");
    expect(screen.getByText("sections/introduction.tex")).toBeInTheDocument();
  });

  it("routes Prism review actions through the workspace Prism surface", () => {
    render(
      <ExecutionCard
        record={makeRecord({
          result_summary: "写作结果已进入 Prism 待复核区",
          result: {
            data: { latex_project_id: "latex-1" },
          },
          next_actions: [
            {
              action: "open_prism",
              label: "在 WenjinPrism 中继续编辑",
            },
          ],
        })}
        phases={[]}
        isExpanded
        onToggle={() => {}}
        selectedNodeId={null}
        selectNode={() => {}}
      />,
    );

    expect(
      screen.getByRole("link", { name: "在 WenjinPrism 中继续编辑" }),
    ).toHaveAttribute("href", "/workspaces/ws-1/prism");
  });

  it("filters unsupported next actions instead of rendering unlabeled workflow escapes", () => {
    render(
      <ExecutionCard
        record={makeRecord({
          result_summary: "写作结果已进入 Prism 待复核区",
          result: {
            data: {
              latex_project_id: "latex-1",
            },
          },
          next_actions: [
            {
              action: "preview_prism_changes",
              label: "预览待复核修改",
              project_id: "latex-1",
            },
            {
              action: "teleport_to_editor",
              label: "跳转到神秘编辑器",
              url: "/mystery",
            },
          ],
        })}
        phases={[]}
        isExpanded
        onToggle={() => {}}
        selectedNodeId={null}
        selectNode={() => {}}
      />,
    );

    expect(
      screen.getByRole("link", { name: "预览待复核修改" }),
    ).toHaveAttribute("href", "/workspaces/ws-1/prism?focus=file_changes");
    expect(
      screen.queryByRole("link", { name: "跳转到神秘编辑器" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("跳转到神秘编辑器")).not.toBeInTheDocument();
  });

  it("renders legacy node details without raw input or output payloads", () => {
    render(
      <ExecutionCard
        record={makeRecord({
          status: "running",
          progress: 42,
          graph_structure: {
            nodes: [
              {
                id: "legacy-node",
                type: "agent_invocation",
                phase: "analysis",
                label: "Legacy node",
              },
            ],
            edges: [],
          },
          node_states: {
            "legacy-node": {
              status: "running",
              input: {
                prompt: "raw input should stay hidden",
              },
              output: {
                status: "running",
                stdout: "raw stdout should stay hidden",
                stderr: "raw stderr should stay hidden",
                output_refs: ["/workspace/outputs/harness/exec-1/node/raw.txt"],
              },
              thinking: "正在整理分析结果。",
            },
          },
        })}
        phases={[
          {
            name: "analysis",
            index: 0,
            nodes: [
              {
                id: "legacy-node",
                type: "agent_invocation",
                phase: "analysis",
                label: "Legacy node",
              },
            ],
          },
        ]}
        isExpanded
        onToggle={() => {}}
        selectedNodeId={null}
        selectNode={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Legacy node" }));

    expect(screen.getByText("状态：运行中")).toBeInTheDocument();
    expect(screen.getByText(/可恢复引用/)).toBeInTheDocument();
    expect(screen.queryByText("Input")).not.toBeInTheDocument();
    expect(screen.queryByText("Output")).not.toBeInTheDocument();
    expect(screen.queryByText(/raw input should stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw stdout should stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw stderr should stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/workspace\/outputs\/harness/)).not.toBeInTheDocument();
  });

  it("sanitizes legacy phase thinking previews", () => {
    render(
      <ExecutionCard
        record={makeRecord({
          status: "running",
          progress: 42,
          graph_structure: {
            nodes: [
              {
                id: "thinking-node",
                type: "agent_invocation",
                phase: "analysis",
                label: "Thinking node",
              },
            ],
            edges: [],
          },
          node_states: {
            "thinking-node": {
              status: "running",
              thinking:
                '{"stdout":"raw stdout should stay hidden","ref":"/workspace/outputs/harness/exec-1/thinking.txt"}',
            },
          },
        })}
        phases={[
          {
            name: "analysis",
            index: 0,
            nodes: [
              {
                id: "thinking-node",
                type: "agent_invocation",
                phase: "analysis",
                label: "Thinking node",
              },
            ],
          },
        ]}
        isExpanded
        onToggle={() => {}}
        selectedNodeId={null}
        selectNode={() => {}}
      />,
    );

    expect(screen.getByText("当前步骤正在处理。")).toBeInTheDocument();
    expect(screen.queryByText(/stdout/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw stdout should stay hidden/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\/workspace\/outputs\/harness/)).not.toBeInTheDocument();
  });
});
