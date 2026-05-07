import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { SubagentGrid } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/SubagentGrid";
import type { SubagentSnap } from "@/stores/workflow-store-support";

function makeSubagent(id: string, status: SubagentSnap["status"]): SubagentSnap {
  return { task_id: id, status };
}

describe("SubagentGrid", () => {
  it("3-card all-running grid: all 3 visible", () => {
    const subagents = [
      makeSubagent("a1", "running"),
      makeSubagent("a2", "running"),
      makeSubagent("a3", "running"),
    ];
    render(<SubagentGrid subagents={subagents} />);
    expect(screen.getByTestId("subagent-card-a1")).toBeInTheDocument();
    expect(screen.getByTestId("subagent-card-a2")).toBeInTheDocument();
    expect(screen.getByTestId("subagent-card-a3")).toBeInTheDocument();
  });

  it("7-card grid (4 completed + 3 running): only 3 running visible by default; fold button present", () => {
    const subagents = [
      makeSubagent("c1", "completed"),
      makeSubagent("c2", "completed"),
      makeSubagent("c3", "completed"),
      makeSubagent("c4", "completed"),
      makeSubagent("r1", "running"),
      makeSubagent("r2", "running"),
      makeSubagent("r3", "running"),
    ];
    render(<SubagentGrid subagents={subagents} />);
    expect(screen.queryByTestId("subagent-card-c1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("subagent-card-c2")).not.toBeInTheDocument();
    expect(screen.queryByTestId("subagent-card-c3")).not.toBeInTheDocument();
    expect(screen.queryByTestId("subagent-card-c4")).not.toBeInTheDocument();
    expect(screen.getByTestId("subagent-card-r1")).toBeInTheDocument();
    expect(screen.getByTestId("subagent-card-r2")).toBeInTheDocument();
    expect(screen.getByTestId("subagent-card-r3")).toBeInTheDocument();

    expect(screen.getByText(/4 个已完成/)).toBeInTheDocument();
  });

  it("click toggle expands the 4 completed cards too", () => {
    const subagents = [
      makeSubagent("c1", "completed"),
      makeSubagent("c2", "completed"),
      makeSubagent("c3", "completed"),
      makeSubagent("c4", "completed"),
      makeSubagent("r1", "running"),
      makeSubagent("r2", "running"),
      makeSubagent("r3", "running"),
    ];
    render(<SubagentGrid subagents={subagents} />);
    const toggle = screen.getByText(/4 个已完成/);
    fireEvent.click(toggle);
    expect(screen.getByTestId("subagent-card-c1")).toBeInTheDocument();
    expect(screen.getByTestId("subagent-card-c2")).toBeInTheDocument();
    expect(screen.getByTestId("subagent-card-c3")).toBeInTheDocument();
    expect(screen.getByTestId("subagent-card-c4")).toBeInTheDocument();
  });

  it("1-card grid: not 2-col (assert via class string)", () => {
    const subagents = [makeSubagent("a1", "running")];
    render(<SubagentGrid subagents={subagents} />);
    const grid = screen.getByTestId("subagent-grid");
    expect(grid.className).not.toContain("grid-cols-2");
  });
});
