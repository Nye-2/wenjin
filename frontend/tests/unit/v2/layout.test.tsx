import { Suspense } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";

const mockUseSearchParams = vi.fn(() => new URLSearchParams());

vi.mock("next/navigation", () => ({
  useSearchParams: () => mockUseSearchParams(),
}));

import V2Page from "@/app/(workbench)/workspaces/[id]/page";

describe("V2 Workspace page", () => {
  beforeEach(() => {
    mockUseSearchParams.mockReset();
    mockUseSearchParams.mockReturnValue(new URLSearchParams());
  });

  it("renders chat / panel / topbar zones", async () => {
    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <V2Page params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>
      );
    });
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-panel")).toBeInTheDocument();
    expect(screen.getByTestId("rooms-topbar")).toBeInTheDocument();
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

  it("opens the requested room from the URL seed", async () => {
    mockUseSearchParams.mockReturnValue(new URLSearchParams("room=documents"));

    await act(async () => {
      render(
        <Suspense fallback={<div>Loading</div>}>
          <V2Page params={Promise.resolve({ id: "ws-1" })} />
        </Suspense>
      );
    });

    expect(screen.getByTestId("documents-drawer")).toBeInTheDocument();
  });

  it("passes room route seeds down to the opened drawer", async () => {
    mockUseSearchParams.mockReturnValue(
      new URLSearchParams("room=documents&item_id=doc-2&query=outline"),
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
});
