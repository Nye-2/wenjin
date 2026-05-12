import { Suspense } from "react";
import { describe, expect, it } from "vitest";
import { render, screen, act } from "@testing-library/react";
import V2Page from "@/app/(workbench)/workspaces/[id]/page";

describe("V2 Workspace page", () => {
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
});
