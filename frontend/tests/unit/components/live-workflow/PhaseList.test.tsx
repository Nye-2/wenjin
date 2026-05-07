import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { PhaseList } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/PhaseList";
import { useWorkflowStore } from "@/stores/workflow-store";
import type { PhaseSnap } from "@/stores/workflow-store-support";

vi.mock("@/stores/workflow-store", () => ({
  useWorkflowStore: vi.fn(),
}));

function makePhase(
  index: number,
  name: string,
  statuses: PhaseSnap["subagents"][number]["status"][],
): PhaseSnap {
  return {
    index,
    name,
    subagents: statuses.map((status, i) => ({
      task_id: `${name}-s${i}`,
      status,
    })),
  };
}

function mockStore(
  overrides: Partial<{ togglePhase: typeof vi.fn; collapsedPhaseIds: Set<string> }> = {},
) {
  const state = {
    togglePhase: vi.fn(),
    collapsedPhaseIds: new Set<string>(),
    ...overrides,
  };
  vi.mocked(useWorkflowStore).mockImplementation(
    ((selector?: (s: unknown) => unknown) => {
      return selector ? selector(state) : state;
    }) as unknown as typeof useWorkflowStore,
  );
  return state;
}

describe("PhaseList", () => {
  it("done phase collapsed by default; running phase expanded", () => {
    mockStore();

    const phases = [
      makePhase(0, "Phase A", ["completed", "completed"]),
      makePhase(1, "Phase B", ["running", "pending"]),
    ];
    render(<PhaseList runId="run-1" phases={phases} />);

    // Phase A is done → collapsed → no subagent cards
    expect(
      screen.queryByTestId("subagent-card-Phase A-s0"),
    ).not.toBeInTheDocument();

    // Phase B is running → expanded → subagent cards visible
    expect(
      screen.getByTestId("subagent-card-Phase B-s0"),
    ).toBeInTheDocument();
  });

  it("header click toggles via togglePhase", () => {
    const { togglePhase } = mockStore();

    const phases = [makePhase(0, "Phase A", ["completed"])];
    render(<PhaseList runId="run-1" phases={phases} />);

    const header = screen.getByText("Phase A").closest("button")!;
    fireEvent.click(header);
    expect(togglePhase).toHaveBeenCalledWith("run-1", 0);
  });

  it("each phase wrapper has the right data-phase-status attribute", () => {
    mockStore();

    const phases = [
      makePhase(0, "Phase A", ["completed", "completed"]),
      makePhase(1, "Phase B", ["running", "pending"]),
      makePhase(2, "Phase C", []),
    ];
    render(<PhaseList runId="run-1" phases={phases} />);

    const wrappers = screen.getAllByTestId("phase-wrapper");
    expect(wrappers[0]).toHaveAttribute("data-phase-status", "done");
    expect(wrappers[1]).toHaveAttribute("data-phase-status", "running");
    expect(wrappers[2]).toHaveAttribute("data-phase-status", "pending");
  });
});
