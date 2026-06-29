import { Suspense } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, act } from "@testing-library/react";
import type { ExecutionRecord } from "@/lib/api/types";
import { useExecutionStore } from "@/stores/execution-store";
import { useWorkbenchLayoutStore } from "@/stores/workbench-layout-store";

const mockUseSearchParams = vi.fn(() => new URLSearchParams());

vi.mock("next/navigation", () => ({
  useSearchParams: () => mockUseSearchParams(),
}));

import V2Page from "@/app/(workbench)/workspaces/[id]/page";

describe("V2 Workspace page", () => {
  beforeEach(() => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    mockUseSearchParams.mockReset();
    mockUseSearchParams.mockReturnValue(new URLSearchParams());
    localStorage.clear();
    useExecutionStore.getState().clear();
    useWorkbenchLayoutStore.getState().reset();
  });

  it("renders chat / panel / workspace chrome zones", async () => {
    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <V2Page params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>
      );
    });
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-panel")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "资料库" })).toBeInTheDocument();
    expect(screen.queryByTestId("rooms-topbar")).not.toBeInTheDocument();
  });

  it("renders the surface switch for workspace-owned Prism navigation", async () => {
    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <V2Page params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>
      );
    });

    expect(screen.getByRole("tab", { name: "Workbench" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "Prism" })).toHaveAttribute(
      "href",
      "/workspaces/ws-1/prism",
    );
  });

  it("keeps a compact route back to the workspace list after removing the side rail", async () => {
    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <V2Page params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>
      );
    });

    expect(screen.getByRole("link", { name: "Wenjin" })).toHaveAttribute(
      "href",
      "/workspaces",
    );
  });

  it("opens existing room drawers from the workspace hub", async () => {
    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <V2Page params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "资料库" }));
    fireEvent.click(screen.getByRole("button", { name: "文献资料" }));

    expect(screen.getByTestId("library-drawer")).toBeInTheDocument();
  });

  it("shows the running status once through the unified workspace chrome", async () => {
    useExecutionStore.getState().upsertExecution(makeRunningRecord());
    useWorkbenchLayoutStore.getState().selectRun("exec-running");
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("run");

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <V2Page params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>
      );
    });

    expect(screen.getAllByText("运行中")).toHaveLength(1);
    expect(screen.getAllByText("中断并补充")).toHaveLength(1);
  });

  it("opens the requested room from the URL seed", async () => {
    mockUseSearchParams.mockReturnValue(new URLSearchParams("room=library"));

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <V2Page params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>
      );
    });

    expect(screen.getByTestId("library-drawer")).toBeInTheDocument();
  });

  it("passes room route seeds down to the opened drawer", async () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams("room=library&item_id=lib-2&query=outline"),
    );

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <V2Page params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>
      );
    });

    const searchInput = screen.getByTestId("drawer-search") as HTMLInputElement;
    expect(searchInput.value).toBe("outline");
  });

  it("ignores removed documents room URL seeds", async () => {
    mockUseSearchParams.mockReturnValue(new URLSearchParams("room=documents"));

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <V2Page params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>
      );
    });

    expect(screen.queryByTestId("documents-drawer")).not.toBeInTheDocument();
    expect(screen.queryByTestId("library-drawer")).not.toBeInTheDocument();
  });

  it("hides chat completely when the workbench is fullscreen", async () => {
    useWorkbenchLayoutStore.getState().setWorkbenchFullscreen(true);

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <V2Page params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>
      );
    });

    expect(screen.queryByTestId("chat-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("workflow-panel")).toBeInTheDocument();
  });
});

function makeRunningRecord(): ExecutionRecord {
  return {
    id: "exec-running",
    user_id: "user-1",
    workspace_id: "ws-1",
    execution_type: "capability",
    feature_id: "outline",
    status: "running",
    params: {},
    node_states: {},
    artifact_ids: [],
    next_actions: [],
    child_execution_ids: [],
    progress: 35,
    created_at: "2026-05-18T00:00:00Z",
    updated_at: "2026-05-18T00:00:05Z",
    started_at: "2026-05-18T00:00:00Z",
    completed_at: null,
    result: null,
  };
}
