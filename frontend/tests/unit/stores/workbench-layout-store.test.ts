import { beforeEach, describe, expect, it } from "vitest";

import { useWorkbenchLayoutStore } from "@/stores/workbench-layout-store";

describe("workbench-layout-store", () => {
  beforeEach(() => {
    localStorage.clear();
    useWorkbenchLayoutStore.getState().reset();
  });

  it("clamps split ratio and resets to the default", () => {
    useWorkbenchLayoutStore.getState().setSplitRatio(0.9);
    expect(useWorkbenchLayoutStore.getState().splitRatio).toBe(0.72);

    useWorkbenchLayoutStore.getState().setSplitRatio(0.2);
    expect(useWorkbenchLayoutStore.getState().splitRatio).toBe(0.28);

    useWorkbenchLayoutStore.getState().resetSplitRatio();
    expect(useWorkbenchLayoutStore.getState().splitRatio).toBe(0.62);
  });

  it("tracks fullscreen without retaining retired run, node, or tab state", () => {
    useWorkbenchLayoutStore.getState().setWorkbenchFullscreen(true);

    expect(useWorkbenchLayoutStore.getState().isWorkbenchFullscreen).toBe(true);
    expect(useWorkbenchLayoutStore.getState()).not.toHaveProperty("activeWorkbenchTab");
    expect(useWorkbenchLayoutStore.getState()).not.toHaveProperty("selectedRunId");
    expect(useWorkbenchLayoutStore.getState()).not.toHaveProperty("selectedNodeId");
  });
});
