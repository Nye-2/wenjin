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

  it("tracks fullscreen and lets automatic tab updates follow context", () => {
    useWorkbenchLayoutStore.getState().setWorkbenchFullscreen(true);
    useWorkbenchLayoutStore.getState().setActiveWorkbenchTab("evidence");
    useWorkbenchLayoutStore.getState().setAutoWorkbenchTab("run");

    expect(useWorkbenchLayoutStore.getState().isWorkbenchFullscreen).toBe(true);
    expect(useWorkbenchLayoutStore.getState().activeWorkbenchTab).toBe("run");
  });
});
