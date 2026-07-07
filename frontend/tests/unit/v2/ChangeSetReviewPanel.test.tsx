import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  ChangeSetReviewPanel,
  type ChangeSetReviewActionState,
} from "@/app/(workbench)/workspaces/[id]/components/review-changes/ChangeSetReviewPanel";
import {
  changeSetViewFromResult,
  type RunViewChangeSet,
} from "@/lib/change-set-view";

function makeReviewChangeSet(): RunViewChangeSet {
  const view = changeSetViewFromResult({
    change_set: {
      execution_id: "exec-1",
      workspace_id: "ws-1",
      write_mode: "ask_workspace_write",
      summary: "Review concrete workspace writes.",
      created_at: "2026-06-20T00:00:00Z",
      units: [
        {
          id: "unit-doc-1",
          target: {
            room: "documents",
            object_type: "document",
            object_id: "doc-1",
            path: "outline.md",
          },
          action: "write_document_draft",
          risk: "medium",
          risk_reasons: ["document draft changes require review"],
          default_apply_state: "staged",
          requires_confirmation: true,
          diff: { title: "Thesis outline", summary: "Update outline" },
          provenance: { output_id: "doc-1" },
          rollback: {},
        },
        {
          id: "unit-lib-1",
          target: {
            room: "library",
            object_type: "library_item",
            object_id: "lib-1",
          },
          action: "add_library_item",
          risk: "high",
          risk_reasons: ["citation evidence requires manual confirmation"],
          default_apply_state: "blocked",
          requires_confirmation: true,
          diff: { title: "Federated Fine-tuning", summary: "Add source candidate" },
          provenance: { output_id: "lib-1" },
          rollback: {},
        },
      ],
    },
  });
  if (!view) {
    throw new Error("expected test change set view");
  }
  return view;
}

function renderPanel({
  actionState,
}: {
  actionState?: ChangeSetReviewActionState;
} = {}) {
  const changeSet = makeReviewChangeSet();
  render(
    <ChangeSetReviewPanel
      changeSet={changeSet}
      pendingReviewCount={changeSet.pendingCount}
      actionState={actionState}
      writeback={{
        committed: false,
        discarded: false,
        reverted: false,
        committing: true,
        reverting: false,
        error: null,
        links: [],
        canSave: true,
        saveCount: 1,
        onSave: vi.fn(),
        onUndo: vi.fn(),
      }}
      onAcceptUnits={vi.fn()}
      onRejectUnits={vi.fn()}
      onUndoUnits={vi.fn()}
    />,
  );
}

describe("ChangeSetReviewPanel accessibility", () => {
  it("announces review and save status updates through live regions", () => {
    renderPanel({
      actionState: {
        executionId: "exec-1",
        action: "accept",
        unitIds: ["unit-doc-1"],
        error: null,
      },
    });

    const reviewStatus = screen.getByRole("status", { name: "复核状态" });
    expect(reviewStatus).toHaveAttribute("aria-live", "polite");
    expect(reviewStatus).toHaveTextContent("正在确认 1 项变更");

    const saveStatus = screen.getByRole("status", { name: "保存状态" });
    expect(saveStatus).toHaveAttribute("aria-live", "polite");
    expect(saveStatus).toHaveTextContent("正在写入工作区");
  });

  it("uses explicit action names and semantic risk tokens", () => {
    renderPanel();

    expect(
      screen.getByRole("button", { name: "全选低/中风险待复核变更" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "清除已选变更" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "查看变更详情 Thesis outline" }),
    ).toBeInTheDocument();

    expect(screen.getAllByText("中风险")[0].getAttribute("style")).toContain(
      "var(--wjn-risk-medium)",
    );
    expect(screen.getAllByText("高风险")[0].getAttribute("style")).toContain(
      "var(--wjn-risk-high)",
    );
  });
});
