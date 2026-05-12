import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { LiveWorkflowPanel } from "@/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel";
import { useExecutionStore } from "@/stores/execution-store";

// Mock @xyflow/react since it requires a real DOM with getBoundingClientRect
vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ children, nodes }: any) => (
    <div data-testid="react-flow-mock" data-node-count={nodes?.length ?? 0}>
      {children}
    </div>
  ),
  Background: () => <div data-testid="background" />,
  Controls: () => <div data-testid="controls" />,
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom" },
}));

// Mock useExecutionStream (SSE subscription) — not needed for unit tests
vi.mock("@/hooks/useExecutionStream", () => ({
  useExecutionStream: () => ({ disconnect: () => {} }),
}));

beforeEach(() => {
  useExecutionStore.getState().clear();
});

describe("LiveWorkflowPanel", () => {
  it("renders empty state when no execution", () => {
    render(
      <LiveWorkflowPanel workspaceId="ws-1" data-testid="workflow-panel" />,
    );
    expect(screen.getByTestId("workflow-panel")).toBeInTheDocument();
    expect(screen.getByText("No active execution")).toBeInTheDocument();
  });

  it("renders graph when execution has nodes", () => {
    useExecutionStore.getState().upsertExecution({
      id: "exec-1",
      user_id: "u1",
      execution_type: "feature",
      status: "running",
      params: {},
      node_states: {
        n1: { status: "completed" },
        n2: { status: "running" },
      },
      artifact_ids: [],
      next_actions: [],
      child_execution_ids: [],
      progress: 0.5,
      created_at: "2026-01-01",
      updated_at: "2026-01-01",
      graph_structure: {
        nodes: [
          { id: "n1", type: "task", label: "Search" },
          { id: "n2", type: "task", label: "Analyze" },
        ],
        edges: [{ from: "n1", to: "n2" }],
      },
    });

    render(
      <LiveWorkflowPanel workspaceId="ws-1" data-testid="workflow-panel" />,
    );
    expect(screen.getByTestId("react-flow-mock")).toBeInTheDocument();
    expect(screen.getByTestId("background")).toBeInTheDocument();
  });

  it("does not render the node detail drawer when no node is selected", () => {
    useExecutionStore.getState().upsertExecution({
      id: "exec-1",
      user_id: "u1",
      execution_type: "feature",
      status: "running",
      params: {},
      node_states: {
        n1: { status: "completed" },
      },
      artifact_ids: [],
      next_actions: [],
      child_execution_ids: [],
      progress: 0.5,
      created_at: "2026-01-01",
      updated_at: "2026-01-01",
      graph_structure: {
        nodes: [{ id: "n1", type: "task", label: "Search" }],
        edges: [],
      },
    });

    render(
      <LiveWorkflowPanel workspaceId="ws-1" data-testid="workflow-panel" />,
    );
    expect(screen.queryByTestId("node-detail-drawer")).not.toBeInTheDocument();
  });
});
