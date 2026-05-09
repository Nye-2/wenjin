import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { LiveWorkflowPanel } from "@/app/(workbench)/workspaces/[id]/components/live-workflow/LiveWorkflowPanel";
import { useWorkflowStore } from "@/stores/workflow-store";
import type { Run } from "@/stores/workflow-store-support";

vi.mock("@/stores/workflow-store", () => ({
  useWorkflowStore: vi.fn(),
}));



function mockStore(overrides: Partial<ReturnType<typeof useWorkflowStore>> = {}) {
  const state = {
    runs: [] as Run[],
    currentRunId: null as string | null,
    pausedRunIds: new Set<string>(),
    collapsedRunIds: new Set<string>(),
    collapsedPhaseIds: new Set<string>(),
    followCurrent: true,
    setFollow: vi.fn(),
    toggleRun: vi.fn(),
    togglePhase: vi.fn(),
    pauseRun: vi.fn(),
    resumeRun: vi.fn(),
    ...overrides,
  };
  vi.mocked(useWorkflowStore).mockImplementation(
    ((selector?: (s: unknown) => unknown) => {
      return selector ? selector(state) : state;
    }) as unknown as typeof useWorkflowStore,
  );
  return state;
}

describe("LiveWorkflowPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("empty state: no runs → no run-list, but workspace-assets is present (default open)", () => {
    mockStore({ runs: [] });
    render(<LiveWorkflowPanel workspaceId="ws-1" />);
    expect(screen.queryByTestId("run-list")).not.toBeInTheDocument();
    expect(screen.getByTestId("workspace-assets")).toBeInTheDocument();
  });

  it("1 run in store → run-list renders", () => {
    const run: Run = {
      id: "run-1",
      thread_id: "t-1",
      title: "论文分析",
      phases: [],
      status: "running",
      started_at: new Date().toISOString(),
    };
    mockStore({ runs: [run], currentRunId: "run-1" });
    render(<LiveWorkflowPanel workspaceId="ws-1" />);
    expect(screen.getByTestId("run-list")).toBeInTheDocument();
  });

  it("pause button calls pauseRun(currentRunId) when not paused", () => {
    const run: Run = {
      id: "run-1",
      thread_id: "t-1",
      title: "论文分析",
      phases: [],
      status: "running",
      started_at: new Date().toISOString(),
    };
    const { pauseRun } = mockStore({
      runs: [run],
      currentRunId: "run-1",
      pausedRunIds: new Set(),
    });
    render(<LiveWorkflowPanel workspaceId="ws-1" />);
    const btn = screen.getByText(/在下个安全点暂停/);
    fireEvent.click(btn);
    expect(pauseRun).toHaveBeenCalledWith("run-1");
  });

  it("shows 继续 button when current run is paused", () => {
    const run: Run = {
      id: "run-1",
      thread_id: "t-1",
      title: "论文分析",
      phases: [],
      status: "running",
      started_at: new Date().toISOString(),
    };
    const { resumeRun } = mockStore({
      runs: [run],
      currentRunId: "run-1",
      pausedRunIds: new Set(["run-1"]),
    });
    render(<LiveWorkflowPanel workspaceId="ws-1" />);
    const btn = screen.getByText(/继续/);
    fireEvent.click(btn);
    expect(resumeRun).toHaveBeenCalledWith("run-1");
  });

  describe("auto-scroll & follow-current (T14)", () => {
    it("auto-scrolls to running phase on mount when followCurrent=true", () => {
      const scrollSpy = vi.fn();
      Element.prototype.scrollIntoView = scrollSpy;

      const run: Run = {
        id: "run-1",
        thread_id: "t-1",
        title: "x",
        phases: [
          {
            index: 0,
            name: "p0",
            subagents: [{ task_id: "a", status: "completed" }],
          },
          {
            index: 1,
            name: "p1",
            subagents: [{ task_id: "b", status: "running" }],
          },
        ],
        status: "running",
        started_at: new Date().toISOString(),
      };
      mockStore({
        runs: [run],
        currentRunId: "run-1",
        followCurrent: true,
      });

      render(<LiveWorkflowPanel workspaceId="ws-1" />);
      expect(scrollSpy).toHaveBeenCalled();
    });

    it("does NOT auto-scroll when followCurrent=false", () => {
      const scrollSpy = vi.fn();
      Element.prototype.scrollIntoView = scrollSpy;

      const run: Run = {
        id: "run-1",
        thread_id: "t-1",
        title: "x",
        phases: [
          {
            index: 1,
            name: "p1",
            subagents: [{ task_id: "b", status: "running" }],
          },
        ],
        status: "running",
        started_at: new Date().toISOString(),
      };
      mockStore({
        runs: [run],
        currentRunId: "run-1",
        followCurrent: false,
      });

      render(<LiveWorkflowPanel workspaceId="ws-1" />);
      expect(scrollSpy).not.toHaveBeenCalled();
    });

    it("'回到当前进度' button shows when follow paused and there's an active run", () => {
      const run: Run = {
        id: "run-1",
        thread_id: "t-1",
        title: "x",
        phases: [
          {
            index: 0,
            name: "p0",
            subagents: [{ task_id: "a", status: "running" }],
          },
        ],
        status: "running",
        started_at: new Date().toISOString(),
      };
      mockStore({
        runs: [run],
        currentRunId: "run-1",
        followCurrent: false,
      });

      render(<LiveWorkflowPanel workspaceId="ws-1" />);
      expect(screen.getByText(/回到当前进度/)).toBeInTheDocument();
    });

    it("'回到当前进度' is hidden when follow is active", () => {
      const run: Run = {
        id: "run-1",
        thread_id: "t-1",
        title: "x",
        phases: [],
        status: "running",
        started_at: new Date().toISOString(),
      };
      mockStore({
        runs: [run],
        currentRunId: "run-1",
        followCurrent: true,
      });

      render(<LiveWorkflowPanel workspaceId="ws-1" />);
      expect(screen.queryByText(/回到当前进度/)).not.toBeInTheDocument();
    });

    it("clicking '回到当前进度' calls setFollow(true)", () => {
      const run: Run = {
        id: "run-1",
        thread_id: "t-1",
        title: "x",
        phases: [
          {
            index: 0,
            name: "p0",
            subagents: [{ task_id: "a", status: "running" }],
          },
        ],
        status: "running",
        started_at: new Date().toISOString(),
      };
      const { setFollow } = mockStore({
        runs: [run],
        currentRunId: "run-1",
        followCurrent: false,
      });

      Element.prototype.scrollIntoView = vi.fn();
      render(<LiveWorkflowPanel workspaceId="ws-1" />);
      fireEvent.click(screen.getByText(/回到当前进度/));
      expect(setFollow).toHaveBeenCalledWith(true);
    });
  });
});
