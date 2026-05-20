import { render, screen } from "@testing-library/react";
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
          result_summary: "写作结果已进入 Prism 待确认区",
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
              label: "预览待确认修改",
              project_id: "latex-1",
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

    expect(screen.getByText("写作结果已进入 Prism 待确认区")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "预览待确认修改" }),
    ).toHaveAttribute("href", "/workspaces/ws-1/prism?focus=file_changes");
    expect(
      screen.getByRole("link", { name: "在 WenjinPrism 中继续编辑" }),
    ).toHaveAttribute("href", "/workspaces/ws-1/prism");
    expect(screen.getByText("sections/introduction.tex")).toBeInTheDocument();
  });

  it("routes Prism review actions through the workspace Prism surface", () => {
    render(
      <ExecutionCard
        record={makeRecord({
          result_summary: "写作结果已进入 Prism 待确认区",
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
          result_summary: "写作结果已进入 Prism 待确认区",
          result: {
            data: {
              latex_project_id: "latex-1",
            },
          },
          next_actions: [
            {
              action: "preview_prism_changes",
              label: "预览待确认修改",
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
      screen.getByRole("link", { name: "预览待确认修改" }),
    ).toHaveAttribute("href", "/workspaces/ws-1/prism?focus=file_changes");
    expect(
      screen.queryByRole("link", { name: "跳转到神秘编辑器" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("跳转到神秘编辑器")).not.toBeInTheDocument();
  });
});
