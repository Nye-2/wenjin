import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorkspaceHubDrawer } from "@/app/(workbench)/workspaces/[id]/components/shell/WorkspaceHubDrawer";

describe("WorkspaceHubDrawer", () => {
  it("presents room entry points as a lightweight hub without technical identifiers", () => {
    const handleRoomSelect = vi.fn();

    render(
      <WorkspaceHubDrawer
        open
        activeRoom={null}
        pendingReviewCount={2}
        completedRunCount={1}
        onClose={() => undefined}
        onRoomSelect={handleRoomSelect}
      />,
    );

    expect(screen.getByRole("dialog", { name: "资料库" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "文献资料" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "文档成果" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行记录，1 项新完成" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认与决策，2 项待确认" })).toBeInTheDocument();
    expect(screen.queryByText(/workspace/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sandbox/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "文献资料" }));

    expect(handleRoomSelect).toHaveBeenCalledWith("library");
  });

  it("closes from Escape and backdrop without selecting a room", () => {
    const handleClose = vi.fn();
    const handleRoomSelect = vi.fn();

    render(
      <WorkspaceHubDrawer
        open
        activeRoom={null}
        pendingReviewCount={0}
        completedRunCount={0}
        onClose={handleClose}
        onRoomSelect={handleRoomSelect}
      />,
    );

    fireEvent.keyDown(window, { key: "Escape" });

    expect(handleClose).toHaveBeenCalledTimes(1);
    expect(handleRoomSelect).not.toHaveBeenCalled();

    fireEvent.mouseDown(screen.getByTestId("workspace-hub-backdrop"));

    expect(handleClose).toHaveBeenCalledTimes(2);
    expect(handleRoomSelect).not.toHaveBeenCalled();
  });
});
