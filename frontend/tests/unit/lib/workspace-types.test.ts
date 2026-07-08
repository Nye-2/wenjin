import { describe, expect, it } from "vitest";

import { WORKSPACE_TYPE_CONFIG } from "@/lib/workspace-type-config";
import { WORKSPACE_TYPES, type WorkspaceType } from "@/lib/workspace-types";
import { isWorkspaceThreadCockpitEnabled } from "@/lib/workspace-rollout";

function workspace(type: WorkspaceType) {
  return {
    id: "workspace-1",
    user_id: "user-1",
    name: "Workspace",
    type,
    config: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("workspace type registry", () => {
  it("exposes math modeling as a first-class workspace type", () => {
    expect(WORKSPACE_TYPES).toContain("math_modeling");
    expect(WORKSPACE_TYPE_CONFIG.math_modeling.title).toBe("数学建模工作台");
    expect(WORKSPACE_TYPE_CONFIG.math_modeling.welcome.body).toContain("上传赛题 PDF");
    expect(WORKSPACE_TYPE_CONFIG.math_modeling.welcome.chips).toHaveLength(4);
    expect(isWorkspaceThreadCockpitEnabled(workspace("math_modeling"))).toBe(true);
  });
});
